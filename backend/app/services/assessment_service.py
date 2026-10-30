"""Assessment orchestration: evidence retrieval -> rule evaluation -> immutable results -> findings."""

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.controls.base import EFFECTIVE, INEFFECTIVE, NEEDS_REVIEW, NOT_ASSESSED, EvidenceInput, RuleOutcome
from app.controls.engine import compute_input_hash, evaluate_scope
from app.controls.rules import ControlRule, get_rule
from app.core.audit import record_audit
from app.core.time import utcnow
from app.models import (
    Asset,
    AssessmentRun,
    Control,
    ControlAssessment,
    ControlAssetScope,
    Evidence,
    Finding,
    RemediationActivity,
    RiskControlMapping,
    RiskFindingMapping,
    RiskServiceMapping,
    User,
)
from app.models.enums import FREQUENCY_DAYS, UNRESOLVED_FINDING_STATUSES
from app.risk.scoring import ScoringInputs, calculate_risk_score
from app.services import settings_service
from app.services.evidence_service import verify_integrity
from app.services.graph_service import GraphContext, load_graph

ADVISORY_LOCK_KEY = 7311001

FINDING_TITLES = {
    "privileged_mfa": "Privileged accounts without MFA",
    "privileged_access_review": "Privileged access review overdue",
    "critical_vuln_sla": "Critical vulnerability remediation SLA breached",
    "internet_vuln_exposure": "Unresolved high-risk vulnerabilities on internet-facing asset",
    "security_logging_coverage": "Security logging coverage gap",
    "endpoint_protection": "Endpoint protection not operating",
    "backup_recovery_test": "Backup recovery test overdue",
    "production_change_approval": "Production changes without approval",
    "encryption_at_rest": "Unencrypted data storage",
    "third_party_assessment": "Third-party security assessment expired",
}

_process_lock = threading.Lock()


class AssessmentInProgressError(RuntimeError):
    pass


@dataclass
class _Evaluated:
    scope: ControlAssetScope
    control: Control
    rule: ControlRule
    params: dict
    context: dict
    evidence: Evidence | None
    evidence_input: EvidenceInput | None
    outcome: RuleOutcome


def _to_input(ev: Evidence | None) -> EvidenceInput | None:
    if ev is None:
        return None
    return EvidenceInput(
        evidence_id=ev.id,
        category=ev.evidence_category,
        sha256=ev.sha256,
        collected_at=ev.collected_at,
        validation_status=ev.validation_status,
        payload=ev.payload,
    )


def asset_context(asset: Asset) -> dict:
    return {
        "asset_id": asset.id,
        "internet_exposed": asset.internet_exposed,
        "environment": asset.environment,
        "criticality": asset.criticality,
    }


def _latest_evidence(db: Session, asset_ids: set[str], categories: set[str], as_of: datetime) -> dict:
    if not asset_ids:
        return {}
    rn = (
        func.row_number()
        .over(
            partition_by=(Evidence.asset_id, Evidence.evidence_category),
            order_by=(Evidence.collected_at.desc(), Evidence.id.desc()),
        )
        .label("rn")
    )
    sub = (
        select(Evidence.id.label("id"), rn)
        .where(
            Evidence.asset_id.in_(asset_ids),
            Evidence.evidence_category.in_(categories),
            Evidence.collected_at <= as_of,
        )
        .subquery()
    )
    latest_ids = select(sub.c.id).where(sub.c.rn == 1)
    rows = db.scalars(select(Evidence).where(Evidence.id.in_(latest_ids))).all()
    return {(e.asset_id, e.evidence_category): e for e in rows}


def _specifics(rule_key: str, details: dict) -> str:
    if rule_key == "privileged_mfa" and details.get("accounts_without_mfa"):
        return "Accounts requiring MFA enrolment: " + ", ".join(details["accounts_without_mfa"]) + "."
    if rule_key in ("critical_vuln_sla",) and details.get("breaches"):
        return "Breaching items: " + ", ".join(b["cve_id"] or b["vuln_id"] for b in details["breaches"][:5]) + "."
    if rule_key == "internet_vuln_exposure" and details.get("exposed_vulnerabilities"):
        return "Exposed items: " + ", ".join(
            v["cve_id"] or v["vuln_id"] for v in details["exposed_vulnerabilities"][:5]
        ) + "."
    if rule_key == "security_logging_coverage" and details.get("gaps"):
        return "Restore sources: " + ", ".join(g["source_type"] for g in details["gaps"]) + "."
    if rule_key == "production_change_approval" and details.get("unapproved_changes"):
        return "Unapproved changes: " + ", ".join(details["unapproved_changes"][:8]) + "."
    if rule_key == "encryption_at_rest" and details.get("unencrypted_volumes"):
        return "Unencrypted volumes: " + ", ".join(details["unencrypted_volumes"]) + "."
    return ""


def _activity(db, finding, activity_type, message, *, at, assessment_id=None, frm=None, to=None, actor=None):
    db.add(
        RemediationActivity(
            finding_id=finding.id,
            actor_id=actor.id if actor else None,
            activity_type=activity_type,
            from_status=frm,
            to_status=to,
            message=message,
            assessment_id=assessment_id,
            created_at=at,
        )
    )


def _link_risks(db: Session, finding: Finding) -> None:
    """Map a new finding to register risks that rely on its control and share an affected service."""
    risk_ids = db.scalars(select(RiskControlMapping.risk_id).where(RiskControlMapping.control_id == finding.control_id))
    impacted = set(finding.impacted_service_ids or [])
    for rid in risk_ids.all():
        services = set(db.scalars(select(RiskServiceMapping.service_id).where(RiskServiceMapping.risk_id == rid)))
        if not services or services & impacted:
            db.add(RiskFindingMapping(risk_id=rid, finding_id=finding.id))


def _score(ev: _Evaluated, gctx: GraphContext, statuses: dict, scoring_cfg: dict) -> tuple[dict, list]:
    asset = ev.scope.asset
    services = gctx.impacted_services_sorted(asset.id)
    top = services[0] if services else None
    comp = [
        {
            "control_id": c["control_id"],
            "credit": c["credit"],
            "status": statuses.get((c["control_id"], asset.id), NOT_ASSESSED),
        }
        for c in ev.params.get("compensating_controls", [])
    ]
    breakdown = calculate_risk_score(
        ScoringInputs(
            control_id=ev.control.id,
            control_name=ev.control.name,
            control_severity=ev.control.failure_severity,
            failure_magnitude=ev.outcome.failure_magnitude,
            asset_id=asset.id,
            asset_criticality=asset.criticality,
            internet_exposed=asset.internet_exposed,
            privileged_access_hub=asset.privileged_access_hub,
            exploit_applicable=ev.rule.evidence_category == "vulnerability_scan",
            exploit_signal=ev.outcome.exploit_signal,
            highest_service_tier=top.tier if top else None,
            highest_service_name=top.name if top else None,
            impacted_service_count=len(services),
            compensating_controls=comp,
        ),
        scoring_cfg.get("weights"),
        scoring_cfg.get("bands"),
    )
    return breakdown, services


def _business_impact(ev: _Evaluated, services: list) -> str:
    asset = ev.scope.asset
    if not services:
        return (
            f"Potential exposure is limited to {asset.name} ({asset.id}); no mapped business service depends on it."
        )
    names = ", ".join(f"{s.name} ({s.tier})" for s in services[:4])
    more = f" and {len(services) - 4} more" if len(services) > 4 else ""
    return (
        f"Potential exposure: {asset.name} ({asset.id}) is in the dependency path of {len(services)} business "
        f"service(s): {names}{more}. The failed control addresses: {ev.control.risk_addressed.rstrip('.')}. "
        "This indicates potential exposure, not a confirmed service disruption."
    )


def run_assessment(
    db: Session,
    *,
    triggered_by: User | None,
    trigger: str = "manual",
    as_of: datetime | None = None,
    control_ids: list[str] | None = None,
    graph_ctx: GraphContext | None = None,
    ip_address: str = "",
) -> AssessmentRun:
    if not _process_lock.acquire(blocking=False):
        raise AssessmentInProgressError("An assessment run is already in progress")
    try:
        if db.get_bind().dialect.name == "postgresql":
            got = db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar()
            if not got:
                raise AssessmentInProgressError("An assessment run is already in progress")
        run = _execute(db, triggered_by, trigger, as_of, control_ids, graph_ctx)
        record_audit(
            db,
            "assessment.run",
            actor=triggered_by,
            entity_type="assessment_run",
            entity_id=run.ref,
            details={"trigger": trigger, **{k: v for k, v in run.summary.items() if k != "status_changes"}},
            ip_address=ip_address,
        )
        db.commit()
        return run
    except Exception:
        db.rollback()
        raise
    finally:
        _process_lock.release()


def _execute(db, triggered_by, trigger, as_of, control_ids, graph_ctx) -> AssessmentRun:
    started = time.perf_counter()
    now = utcnow()
    as_of = as_of or now
    run = AssessmentRun(
        trigger=trigger,
        triggered_by_id=triggered_by.id if triggered_by else None,
        scope_description=("Controls: " + ", ".join(control_ids)) if control_ids else "All active controls",
        evaluated_at=as_of,
        started_at=now,
        status="running",
    )
    db.add(run)
    db.flush()

    controls = {c.id: c for c in db.scalars(select(Control).where(Control.is_active.is_(True)))}
    if control_ids:
        controls = {k: v for k, v in controls.items() if k in control_ids}
    all_scopes = db.scalars(select(ControlAssetScope)).all()
    scopes = [s for s in all_scopes if s.control_id in controls]

    rules = {cid: get_rule(c.rule_key) for cid, c in controls.items()}
    evidence_map = _latest_evidence(
        db, {s.asset_id for s in scopes}, {r.evidence_category for r in rules.values()}, as_of
    )
    gctx = graph_ctx or load_graph(db)
    scoring_cfg = settings_service.get_setting(db, "risk_scoring")
    validation_mode = settings_service.get_setting(db, "validation_workflow").get("mode", "auto_resolve")
    sla_days = settings_service.get_setting(db, "remediation_sla_days")

    active = {
        (f.control_id, f.asset_id): f
        for f in db.scalars(select(Finding).where(Finding.status != "Resolved"))
    }

    evaluated: list[_Evaluated] = []
    for scope in sorted(scopes, key=lambda s: (s.control_id, s.asset_id)):
        control = controls[scope.control_id]
        rule = rules[scope.control_id]
        params = rule.parameters(control.rule_parameters)
        context = asset_context(scope.asset)
        ev = evidence_map.get((scope.asset_id, rule.evidence_category))
        ev_input = _to_input(ev)
        outcome = evaluate_scope(rule, params, context, ev_input, as_of)
        evaluated.append(_Evaluated(scope, control, rule, params, context, ev, ev_input, outcome))

    statuses = {(s.control_id, s.asset_id): s.current_status for s in all_scopes}
    for e in evaluated:
        statuses[(e.scope.control_id, e.scope.asset_id)] = e.outcome.result

    summary = {
        "scopes_evaluated": len(evaluated),
        "controls_evaluated": len(controls),
        "results": {EFFECTIVE: 0, INEFFECTIVE: 0, NEEDS_REVIEW: 0, NOT_ASSESSED: 0},
        "findings_created": [],
        "findings_updated": 0,
        "findings_resolved": [],
        "findings_pending_validation": [],
        "findings_reopened": [],
        "status_changes": [],
    }

    for e in evaluated:
        o = e.outcome
        summary["results"][o.result] += 1
        key = (e.scope.control_id, e.scope.asset_id)
        previous_status = e.scope.current_status
        finding = active.get(key)
        breakdown = services = None

        # 1. Finding create/update (must exist before the immutable assessment row references it).
        if o.result == INEFFECTIVE:
            breakdown, services = _score(e, gctx, statuses, scoring_cfg)
            impact = _business_impact(e, services)
            recommendation = " ".join(p for p in (e.rule.remediation, _specifics(e.rule.key, o.details)) if p)
            if finding is None:
                finding = Finding(
                    title=f"{FINDING_TITLES.get(e.rule.key, e.control.name)}: {e.scope.asset.name}",
                    description=f"{e.control.id} ({e.control.name}) was assessed as Ineffective for "
                    f"{e.scope.asset_id}. {o.explanation}",
                    control_id=e.control.id,
                    asset_id=e.scope.asset_id,
                    service_id=services[0].id if services else None,
                    severity=breakdown["severity"],
                    risk_score=breakdown["score"],
                    score_breakdown=breakdown,
                    business_impact=impact,
                    impacted_service_ids=[s.id for s in services],
                    remediation_recommendation=recommendation,
                    status="Open",
                    assigned_owner_id=e.control.owner_id,
                    detected_at=as_of,
                    last_seen_at=as_of,
                    due_date=as_of + timedelta(days=int(sla_days.get(breakdown["severity"], 30))),
                    created_at=as_of,
                    updated_at=as_of,
                )
                db.add(finding)
                db.flush()
                _link_risks(db, finding)
                active[key] = finding
                summary["findings_created"].append(finding.ref)
                created = True
            else:
                created = False
                finding.description = (
                    f"{e.control.id} ({e.control.name}) was assessed as Ineffective for {e.scope.asset_id}. "
                    f"{o.explanation}"
                )
                finding.risk_score = breakdown["score"]
                finding.severity = breakdown["severity"]
                finding.score_breakdown = breakdown
                finding.business_impact = impact
                finding.impacted_service_ids = [s.id for s in services]
                finding.service_id = services[0].id if services else None
                finding.remediation_recommendation = recommendation
                finding.last_seen_at = as_of
                finding.updated_at = as_of
                summary["findings_updated"] += 1
        else:
            created = False

        assessment = ControlAssessment(
            run_id=run.id,
            control_id=e.control.id,
            asset_id=e.scope.asset_id,
            scope_identifier=f"{e.control.id}:{e.scope.asset_id}",
            assessed_at=as_of,
            recorded_at=now,
            result=o.result,
            rule_key=e.rule.key,
            rule_version=e.rule.version,
            rule_parameters=e.params,
            explanation=o.explanation,
            details={
                **o.details,
                "context": e.context,
                "failure_magnitude": round(o.failure_magnitude, 4),
                "exploit_signal": o.exploit_signal,
                "previous_status": previous_status,
            },
            input_hash=compute_input_hash(e.rule, e.params, e.context, e.evidence_input, as_of),
            finding_id=finding.id if finding is not None else None,
            evidence=[e.evidence] if e.evidence is not None else [],
        )
        db.add(assessment)
        db.flush()

        # 2. Finding lifecycle transitions driven by the assessment result.
        if finding is not None:
            if o.result == INEFFECTIVE:
                finding.latest_assessment_id = assessment.id
                if created:
                    finding.first_assessment_id = assessment.id
                    _activity(
                        db,
                        finding,
                        "detected",
                        f"Detected by {assessment.ref}: {o.explanation} Risk score {finding.risk_score} "
                        f"({finding.severity}).",
                        at=as_of,
                        assessment_id=assessment.id,
                        to="Open",
                    )
                elif finding.status == "Pending Validation":
                    _activity(
                        db,
                        finding,
                        "validation_failed",
                        f"Validation failed: {assessment.ref} is still Ineffective. {o.explanation}",
                        at=as_of,
                        assessment_id=assessment.id,
                        frm="Pending Validation",
                        to="In Progress",
                    )
                    finding.status = "In Progress"
                    finding.validated_by_assessment_id = None
                    summary["findings_reopened"].append(finding.ref)
                elif finding.status == "Risk Accepted" and finding.acceptance_expires_at and finding.acceptance_expires_at <= as_of:
                    _activity(
                        db,
                        finding,
                        "acceptance_expired",
                        f"Risk acceptance expired; {assessment.ref} confirms the control remains Ineffective.",
                        at=as_of,
                        assessment_id=assessment.id,
                        frm="Risk Accepted",
                        to="Open",
                    )
                    finding.status = "Open"
                    summary["findings_reopened"].append(finding.ref)
            elif o.result == EFFECTIVE and finding.status in (*UNRESOLVED_FINDING_STATUSES, "Risk Accepted"):
                frm = finding.status
                evidence_ref = e.evidence.ref if e.evidence is not None else "n/a"
                if validation_mode == "auto_resolve":
                    finding.status = "Resolved"
                    finding.resolved_at = as_of
                    finding.validated_by_assessment_id = assessment.id
                    finding.updated_at = as_of
                    _activity(
                        db,
                        finding,
                        "validated",
                        f"Validated by {assessment.ref} against evidence {evidence_ref}: {o.explanation} "
                        "Finding resolved.",
                        at=as_of,
                        assessment_id=assessment.id,
                        frm=frm,
                        to="Resolved",
                    )
                    summary["findings_resolved"].append(finding.ref)
                    del active[key]
                else:
                    finding.validated_by_assessment_id = assessment.id
                    finding.updated_at = as_of
                    if frm != "Pending Validation":
                        finding.status = "Pending Validation"
                        _activity(
                            db,
                            finding,
                            "reassessment_passed",
                            f"{assessment.ref} passed against evidence {evidence_ref}. Awaiting analyst sign-off "
                            "to resolve.",
                            at=as_of,
                            assessment_id=assessment.id,
                            frm=frm,
                            to="Pending Validation",
                        )
                    summary["findings_pending_validation"].append(finding.ref)
            elif o.result in (NEEDS_REVIEW, NOT_ASSESSED) and previous_status != o.result:
                _activity(
                    db,
                    finding,
                    "inconclusive",
                    f"{assessment.ref} was inconclusive ({o.result}): {o.explanation} Finding status unchanged.",
                    at=as_of,
                    assessment_id=assessment.id,
                )

        if previous_status != o.result:
            summary["status_changes"].append(
                {"control_id": e.control.id, "asset_id": e.scope.asset_id, "from": previous_status, "to": o.result}
            )
        e.scope.current_status = o.result
        e.scope.last_assessed_at = as_of
        e.scope.latest_assessment_id = assessment.id
        if e.scope.asset.last_assessed_at is None or e.scope.asset.last_assessed_at < as_of:
            e.scope.asset.last_assessed_at = as_of

    for control in controls.values():
        statuses_c = [s.current_status for s in all_scopes if s.control_id == control.id]
        control.current_status = aggregate_status(statuses_c)
        control.last_assessed_at = as_of
        control.next_assessment_at = as_of + timedelta(days=FREQUENCY_DAYS[control.frequency])

    summary["duration_ms"] = int((time.perf_counter() - started) * 1000)
    run.summary = summary
    run.status = "completed"
    run.completed_at = utcnow()
    db.flush()
    return run


def aggregate_status(statuses: list[str]) -> str:
    if INEFFECTIVE in statuses:
        return INEFFECTIVE
    if NEEDS_REVIEW in statuses:
        return NEEDS_REVIEW
    if EFFECTIVE in statuses:
        return EFFECTIVE
    return NOT_ASSESSED


def replay_assessment(assessment: ControlAssessment) -> dict:
    """Re-run the recorded rule against the recorded evidence and parameters to verify reproducibility."""
    rule = get_rule(assessment.rule_key)
    ev = assessment.evidence[0] if assessment.evidence else None
    ev_input = _to_input(ev)
    context = assessment.details.get("context", {})
    integrity = verify_integrity(ev) if ev is not None else None
    outcome = evaluate_scope(rule, assessment.rule_parameters, context, ev_input, assessment.assessed_at)
    recomputed_hash = compute_input_hash(rule, assessment.rule_parameters, context, ev_input, assessment.assessed_at)
    checks = {
        "rule_version_matches": rule.version == assessment.rule_version,
        "result_matches": outcome.result == assessment.result,
        "explanation_matches": outcome.explanation == assessment.explanation,
        "input_hash_matches": recomputed_hash == assessment.input_hash,
        "evidence_integrity_verified": integrity["verified"] if integrity else None,
    }
    reproducible = all(v for v in checks.values() if v is not None)
    return {
        "assessment_id": assessment.ref,
        "reproducible": reproducible,
        "checks": checks,
        "replayed_result": outcome.result,
        "replayed_explanation": outcome.explanation,
        "recorded_input_hash": assessment.input_hash,
        "recomputed_input_hash": recomputed_hash,
        "current_rule_version": rule.version,
        "evidence_integrity": integrity,
    }
