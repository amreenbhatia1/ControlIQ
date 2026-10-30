from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permissions as P
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.deps import require
from app.core.rate_limit import client_ip, rate_limit
from app.models import GeneratedReport, User
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Reports"])


def _check(report_type: str):
    if report_type not in report_service.REPORT_TYPES:
        raise HTTPException(404, "Unknown report type")


@router.get("/types", dependencies=[Depends(require(P.READ))])
def types():
    return [{"key": k, "title": v} for k, v in report_service.REPORT_TYPES.items()]


@router.get("/history", dependencies=[Depends(require(P.READ))])
def history(db: Session = Depends(get_db)):
    rows = db.scalars(select(GeneratedReport).order_by(GeneratedReport.generated_at.desc()).limit(30)).all()
    return [{"id": r.id, "ref": r.ref, "report_type": r.report_type, "title": r.title, "period_days": r.period_days,
             "generated_at": r.generated_at, "generated_by": r.generated_by.full_name if r.generated_by else None,
             "sha256": r.sha256} for r in rows]


@router.get("/{report_type}")
def preview(report_type: str, period_days: int = Query(30, ge=7, le=365), db: Session = Depends(get_db),
            user: User = Depends(require(P.REPORTS_GENERATE))):
    _check(report_type)
    return report_service.build_report(db, report_type, period_days, user)


@router.get("/{report_type}/pdf", dependencies=[Depends(rate_limit("report_pdf", 20, 60))])
def pdf(report_type: str, request: Request, period_days: int = Query(30, ge=7, le=365), db: Session = Depends(get_db),
        user: User = Depends(require(P.REPORTS_GENERATE))):
    _check(report_type)
    report = report_service.build_report(db, report_type, period_days, user)
    content = report_service.render_pdf(report)
    digest = report_service.pdf_digest(content)
    rec = GeneratedReport(report_type=report_type, title=report["title"], period_days=period_days, generated_by_id=user.id,
                          sha256=digest, summary=f"{len(report['sections'])} sections")
    db.add(rec)
    db.flush()
    record_audit(db, "report.generate", actor=user, entity_type="report", entity_id=rec.ref,
                 details={"type": report_type, "period_days": period_days, "sha256": digest}, ip_address=client_ip(request))
    db.commit()
    filename = f"ControlIQ_{report_type}_{report['generated_at']:%Y%m%d_%H%M}.pdf"
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "X-Report-Id": rec.ref, "X-Content-SHA256": digest})
