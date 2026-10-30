"""Dashboard metrics. All values are derived from stored records at request time.

Definitions:
- Control instance: a control applied to an asset scope (control_asset_scopes).
- Effectiveness rate: Effective / (Effective + Ineffective + Needs Review) instances; Not Assessed excluded.
- Unresolved finding: status Open, In Progress or Pending Validation.
- Active finding: any status other than Resolved (includes Risk Accepted).
- Business service at risk: a service whose dependency path contains an unresolved High/Critical finding.
"""

from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import (
    AssessmentRun,
    BusinessService,
    Control,
    ControlAssessment,
    ControlAssetScope,
    Finding,
    RemediationAction,
)
from app.models.enums import CONTROL_DOMAINS, SEVERITIES, UNRESOLVED_FINDING_STATUSES
from app.risk.graph import service_exposure_index

ASSESSED = ("Effective", "Ineffective", "Needs Review")


def kpis(db: Session) -> dict:
    status_counts = dict(
        db.execute(
            select(ControlAssetScope.current_status, func.count())
            .join(Control, Control.id == ControlAssetScope.control_id)
            .where(Control.is_active.is_(True))
            .group_by(ControlAssetScope.current_status)
        ).all()
    )
    total = sum(status_counts.values())
    eff = status_counts.get("Effective", 0)
    ineff = status_counts.get("Ineffective", 0)
    review = status_counts.get("Needs Review", 0)
    assessed = eff + ineff + review
    now = utcnow()
    finding_counts = db.execute(
        select(
            func.count().filter(Finding.status.in_(UNRESOLVED_FINDING_STATUSES)),
            func.count().filter(Finding.status.in_(UNRESOLVED_FINDING_STATUSES), Finding.severity == "Critical"),
            func.count().filter(Finding.status == "Risk Accepted"),
            func.count().filter(Finding.status.in_(UNRESOLVED_FINDING_STATUSES), Finding.due_date < now),
        )
    ).one()
    actions = db.execute(
        select(
            func.count().filter(RemediationAction.status.in_(("Planned", "In Progress"))),
            func.count().filter(RemediationAction.status.in_(("Planned", "In Progress")), RemediationAction.due_date < now),
        )
    ).one()
    services_at_risk = len(_services_at_risk_ids(db))
    control_defs = db.scalar(select(func.count()).select_from(Control).where(Control.is_active.is_(True))) or 0
    failing_defs = db.scalar(select(func.count()).select_from(Control).where(Control.current_status == "Ineffective")) or 0
    return {
        "total_control_instances": total,
        "control_definitions": control_defs,
        "control_definitions_failing": failing_defs,
        "effective_controls": eff,
        "failed_controls": ineff,
        "needs_review_controls": review,
        "not_assessed_controls": status_counts.get("Not Assessed", 0),
        "effectiveness_rate": round(100 * eff / assessed, 1) if assessed else None,
        "unresolved_findings": finding_counts[0],
        "critical_findings": finding_counts[1],
        "risk_accepted_findings": finding_counts[2],
        "overdue_findings": finding_counts[3],
        "open_remediation_actions": actions[0],
        "overdue_remediation_actions": actions[1],
        "services_at_risk": services_at_risk,
        "services_total": db.scalar(select(func.count()).select_from(BusinessService)) or 0,
    }


def _unresolved_findings(db: Session) -> list[Finding]:
    return list(db.scalars(select(Finding).where(Finding.status.in_(UNRESOLVED_FINDING_STATUSES))))


def _services_at_risk_ids(db: Session) -> set[str]:
    ids: set[str] = set()
    for f in _unresolved_findings(db):
        if f.severity in ("Critical", "High"):
            ids.update(f.impacted_service_ids or [])
    return ids


def trend(db: Session, days: int) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(
            AssessmentRun.id,
            AssessmentRun.evaluated_at,
            func.sum(case((ControlAssessment.result == "Effective", 1), else_=0)),
            func.sum(case((ControlAssessment.result == "Ineffective", 1), else_=0)),
            func.sum(case((ControlAssessment.result == "Needs Review", 1), else_=0)),
        )
        .join(ControlAssessment, ControlAssessment.run_id == AssessmentRun.id)
        .where(AssessmentRun.evaluated_at >= since, AssessmentRun.status == "completed")
        .group_by(AssessmentRun.id, AssessmentRun.evaluated_at)
        .order_by(AssessmentRun.evaluated_at)
    ).all()
    out = []
    for run_id, at, eff, ineff, review in rows:
        assessed = (eff or 0) + (ineff or 0) + (review or 0)
        out.append(
            {
                "run_id": run_id,
                "evaluated_at": at,
                "effective": eff or 0,
                "ineffective": ineff or 0,
                "needs_review": review or 0,
                "effectiveness_rate": round(100 * (eff or 0) / assessed, 1) if assessed else None,
            }
        )
    return out


def severity_distribution(db: Session) -> list[dict]:
    counts = dict(
        db.execute(
            select(Finding.severity, func.count())
            .where(Finding.status.in_(UNRESOLVED_FINDING_STATUSES))
            .group_by(Finding.severity)
        ).all()
    )
    return [{"severity": s, "count": counts.get(s, 0)} for s in SEVERITIES]


def domain_distribution(db: Session) -> list[dict]:
    rows = db.execute(
        select(Control.domain, Finding.severity, func.count())
        .join(Control, Control.id == Finding.control_id)
        .where(Finding.status.in_(UNRESOLVED_FINDING_STATUSES))
        .group_by(Control.domain, Finding.severity)
    ).all()
    data = {d: {s: 0 for s in SEVERITIES} for d in CONTROL_DOMAINS}
    for domain, sev, n in rows:
        data[domain][sev] = n
    return [{"domain": d, **counts, "total": sum(counts.values())} for d, counts in data.items()]


def services_at_risk(db: Session, limit: int = 10) -> list[dict]:
    services = {s.id: s for s in db.scalars(select(BusinessService))}
    per_service: dict[str, list[Finding]] = {sid: [] for sid in services}
    for f in _unresolved_findings(db):
        for sid in f.impacted_service_ids or []:
            if sid in per_service:
                per_service[sid].append(f)
    out = []
    for sid, findings in per_service.items():
        s = services[sid]
        exposure = service_exposure_index([f.risk_score for f in findings])
        top = max(findings, key=lambda f: f.risk_score) if findings else None
        out.append(
            {
                "service_id": sid,
                "name": s.name,
                "tier": s.tier,
                "unresolved_findings": len(findings),
                "critical_findings": sum(1 for f in findings if f.severity == "Critical"),
                "exposure_index": exposure["index"],
                "exposure_level": exposure["level"],
                "exposure_formula": exposure["formula"],
                "top_finding": None if top is None else {"id": top.id, "ref": top.ref, "title": top.title, "risk_score": top.risk_score},
            }
        )
    out.sort(key=lambda x: (-x["exposure_index"], x["tier"], x["name"]))
    return out[:limit]


def critical_attention(db: Session, limit: int = 5) -> list[Finding]:
    return list(
        db.scalars(
            select(Finding)
            .where(Finding.status.in_(UNRESOLVED_FINDING_STATUSES))
            .order_by(Finding.risk_score.desc(), Finding.detected_at.asc())
            .limit(limit)
        )
    )


def last_run(db: Session) -> AssessmentRun | None:
    return db.scalar(
        select(AssessmentRun).where(AssessmentRun.status == "completed").order_by(AssessmentRun.evaluated_at.desc()).limit(1)
    )
