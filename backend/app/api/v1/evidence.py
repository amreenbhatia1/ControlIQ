import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import assessment_out, evidence_out, paginate_params
from app.controls.evidence_schemas import CSV_LIST_FIELDS, EVIDENCE_CATEGORY_LABELS, EVIDENCE_SCHEMAS
from app.core import permissions as P
from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import require
from app.core.rate_limit import client_ip, rate_limit
from app.core.refs import parse_ref
from app.core.time import parse_iso, utcnow
from app.models import ControlAssessment, Evidence, User, assessment_evidence
from app.schemas.common import Page
from app.schemas.entities import EvidenceOut
from app.seed import evidence_generators as gen
from app.services.evidence_service import EvidenceError, ingest_evidence, read_evidence_file, verify_integrity

router = APIRouter(prefix="/evidence", tags=["Evidence Center"])

SAMPLE_ASSETS = {
    "privileged_accounts": "IDP-CORE-001", "access_review": "PAY-API-001", "vulnerability_scan": "WEB-BANK-001",
    "logging_coverage": "DB-TXN-001", "endpoint_protection": "PAY-SRV-001", "backup_recovery": "DB-CUST-001",
    "change_records": "PAY-API-001", "encryption_status": "DB-CUST-001", "third_party_assessment": "EXT-PAYNET-001",
}
CONTENT_TYPES = {"json": "application/json", "csv": "text/csv", "pdf": "application/pdf", "text": "text/plain"}


@router.get("/categories", dependencies=[Depends(require(P.READ))])
def categories():
    clock = gen.Clock(utcnow())
    out = []
    for key, schema in EVIDENCE_SCHEMAS.items():
        sample = gen.GENERATORS[key](SAMPLE_ASSETS[key], 0, clock)
        out.append({"key": key, "label": EVIDENCE_CATEGORY_LABELS[key], "structured": True,
                    "fields": list(schema.model_fields.keys()), "csv_list_field": CSV_LIST_FIELDS.get(key), "sample": sample})
    out.append({"key": "supporting_document", "label": EVIDENCE_CATEGORY_LABELS["supporting_document"], "structured": False,
                "fields": [], "csv_list_field": None, "sample": None})
    return out


@router.get("", response_model=Page[EvidenceOut], dependencies=[Depends(require(P.READ))])
def list_evidence(q: str | None = Query(None, max_length=100), category: str | None = None, asset_id: str | None = None,
                  control_id: str | None = None, validation_status: str | None = None, uploaded_only: bool = False,
                  page: int = 1, page_size: int = 25, db: Session = Depends(get_db)):
    page, page_size = paginate_params(page, page_size)
    stmt = select(Evidence)
    if q:
        like = f"%{q.strip()}%"
        clauses = [Evidence.original_filename.ilike(like), Evidence.source.ilike(like), Evidence.asset_id.ilike(like),
                   Evidence.sha256.ilike(like)]
        eid = parse_ref("evidence", q)
        if eid:
            clauses.append(Evidence.id == eid)
        stmt = stmt.where(or_(*clauses))
    if category:
        stmt = stmt.where(Evidence.evidence_category == category)
    if asset_id:
        stmt = stmt.where(Evidence.asset_id == asset_id)
    if control_id:
        stmt = stmt.where(Evidence.control_id == control_id)
    if validation_status:
        stmt = stmt.where(Evidence.validation_status == validation_status)
    if uploaded_only:
        stmt = stmt.where(Evidence.uploaded_by_id.is_not(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Evidence.uploaded_at.desc(), Evidence.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[evidence_out(e) for e in rows], total=total, page=page, page_size=page_size)


@router.post("/upload", status_code=201, dependencies=[Depends(rate_limit("evidence_upload", 20, 60))])
async def upload(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    asset_id: str = Form(...),
    source: str = Form("Manual upload", max_length=160),
    control_id: str | None = Form(None),
    collected_at: str | None = Form(None),
    description: str = Form("", max_length=2000),
    db: Session = Depends(get_db),
    user: User = Depends(require(P.EVIDENCE_UPLOAD)),
):
    limit = get_settings().evidence_max_bytes
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"Evidence exceeds the {limit // 1024} KB size limit")
    try:
        collected: datetime | None = parse_iso(collected_at) if collected_at else None
    except ValueError as exc:
        raise HTTPException(422, "collected_at must be an ISO-8601 timestamp") from exc
    try:
        ev = ingest_evidence(db, content=content, filename=file.filename or "evidence", category=category,
                             source=source.strip() or "Manual upload", asset_id=asset_id or None,
                             control_id=control_id or None, collected_at=collected, description=description, uploaded_by=user)
    except EvidenceError as exc:
        db.rollback()
        record_audit(db, "evidence.upload", actor=user, entity_type="evidence", outcome="rejected",
                     details={"reason": str(exc), "filename": (file.filename or "")[:120]}, ip_address=client_ip(request))
        db.commit()
        raise HTTPException(422, str(exc)) from exc
    record_audit(db, "evidence.upload", actor=user, entity_type="evidence", entity_id=ev.ref,
                 details={"category": category, "asset_id": ev.asset_id, "sha256": ev.sha256, "validation": ev.validation_status},
                 ip_address=client_ip(request))
    db.commit()
    return evidence_out(ev)


def _get(db: Session, evidence_id: str) -> Evidence:
    eid = parse_ref("evidence", evidence_id)
    e = db.get(Evidence, eid) if eid else None
    if e is None:
        raise HTTPException(404, "Evidence not found")
    return e


@router.get("/{evidence_id}", dependencies=[Depends(require(P.READ))])
def get_evidence(evidence_id: str, db: Session = Depends(get_db)):
    e = _get(db, evidence_id)
    used = db.scalars(select(ControlAssessment).join(assessment_evidence, assessment_evidence.c.assessment_id == ControlAssessment.id)
                      .where(assessment_evidence.c.evidence_id == e.id).order_by(ControlAssessment.assessed_at.desc()).limit(50)).all()
    preview = None
    if e.file_format == "text":
        try:
            preview = read_evidence_file(e)[:20000].decode("utf-8", errors="replace")
        except (OSError, EvidenceError):
            preview = None
    return {"evidence": evidence_out(e), "payload": e.payload, "text_preview": preview,
            "used_by_assessments": [assessment_out(a) for a in used]}


@router.get("/{evidence_id}/download", dependencies=[Depends(require(P.READ))])
def download(evidence_id: str, db: Session = Depends(get_db)):
    e = _get(db, evidence_id)
    try:
        content = read_evidence_file(e)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Stored evidence file not found") from exc
    if hashlib.sha256(content).hexdigest() != e.sha256:
        raise HTTPException(409, "Stored evidence file failed integrity verification; download blocked")
    safe = "".join(ch for ch in e.original_filename if ch.isalnum() or ch in "._-")[:120] or "evidence"
    return Response(content=content, media_type=CONTENT_TYPES[e.file_format], headers={
        "Content-Disposition": f'attachment; filename="{e.ref}_{safe}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "X-Content-SHA256": e.sha256,
    })


@router.post("/{evidence_id}/verify", dependencies=[Depends(require(P.READ))])
def verify(evidence_id: str, db: Session = Depends(get_db)):
    return {"evidence_id": evidence_id, **verify_integrity(_get(db, evidence_id))}
