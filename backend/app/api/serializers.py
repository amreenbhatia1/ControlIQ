from app.core.refs import make_ref
from app.core.time import utcnow
from app.models import ControlAssessment, Evidence, Finding, User
from app.schemas.entities import AssessmentOut, EvidenceOut, FindingOut


def user_ref(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "title": u.title}


def finding_out(f: Finding) -> FindingOut:
    now = utcnow()
    end = f.resolved_at or now
    return FindingOut(
        id=f.id,
        ref=f.ref,
        title=f.title,
        description=f.description,
        control_id=f.control_id,
        control_name=f.control.name,
        control_domain=f.control.domain,
        asset_id=f.asset_id,
        asset_name=f.asset.name,
        service_id=f.service_id,
        service_name=f.service.name if f.service else None,
        severity=f.severity,
        risk_score=f.risk_score,
        status=f.status,
        assigned_owner=user_ref(f.assigned_owner),
        detected_at=f.detected_at,
        last_seen_at=f.last_seen_at,
        due_date=f.due_date,
        resolved_at=f.resolved_at,
        updated_at=f.updated_at,
        age_days=max(0, (end - f.detected_at).days),
        overdue=f.status in ("Open", "In Progress", "Pending Validation") and f.due_date < now,
    )


def evidence_out(e: Evidence) -> EvidenceOut:
    return EvidenceOut(
        id=e.id,
        ref=e.ref,
        evidence_category=e.evidence_category,
        file_format=e.file_format,
        source=e.source,
        description=e.description,
        collected_at=e.collected_at,
        uploaded_at=e.uploaded_at,
        uploaded_by=e.uploaded_by.full_name if e.uploaded_by else None,
        asset_id=e.asset_id,
        control_id=e.control_id,
        sha256=e.sha256,
        validation_status=e.validation_status,
        validation_errors=e.validation_errors or [],
        original_filename=e.original_filename,
        size_bytes=e.size_bytes,
    )


def assessment_out(a: ControlAssessment, evidence_refs: list[str] | None = None) -> AssessmentOut:
    return AssessmentOut(
        id=a.id,
        ref=a.ref,
        run_id=a.run_id,
        run_ref=make_ref("run", a.run_id),
        control_id=a.control_id,
        control_name=a.control.name,
        asset_id=a.asset_id,
        asset_name=a.asset.name if a.asset else None,
        scope_identifier=a.scope_identifier,
        assessed_at=a.assessed_at,
        recorded_at=a.recorded_at,
        result=a.result,
        rule_key=a.rule_key,
        rule_version=a.rule_version,
        explanation=a.explanation,
        input_hash=a.input_hash,
        finding_id=a.finding_id,
        finding_ref=make_ref("finding", a.finding_id),
        evidence_refs=evidence_refs if evidence_refs is not None else [e.ref for e in a.evidence],
    )


def paginate_params(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    return page, page_size
