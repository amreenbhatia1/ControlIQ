from datetime import timedelta

import pytest
from sqlalchemy import select

from app.controls.base import EvidenceInput
from app.controls.engine import compute_input_hash, evaluate_scope
from app.controls.rules import get_rule
from app.core.time import utcnow
from app.models import ControlAssessment, ControlAssetScope, Finding, RiskFindingMapping
from tests import factory as f


def _latest(db, control_id, asset_id):
    return db.scalar(
        select(ControlAssessment)
        .where(ControlAssessment.control_id == control_id, ControlAssessment.asset_id == asset_id)
        .order_by(ControlAssessment.id.desc())
    )


def _evidence_input(category, payload, collected_at, status="Valid"):
    return EvidenceInput(evidence_id=1, category=category, sha256="0" * 64, collected_at=collected_at,
                         validation_status=status, payload=payload)


# --------------------------------------------------------------------------- successful assessment
def test_successful_assessment_records_effective_result_with_evidence(db, world):
    ev = f.ingest(db, "privileged_accounts", "IDP-CORE-001", f.mfa_payload())
    run = f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])

    a = _latest(db, "CTRL-IAM-001", "IDP-CORE-001")
    assert a.result == "Effective"
    assert a.run_id == run.id
    assert [e.id for e in a.evidence] == [ev.id]
    assert a.rule_key == "privileged_mfa" and a.rule_version == get_rule("privileged_mfa").version
    assert len(a.input_hash) == 64
    assert "All 3 active privileged accounts have MFA enabled" in a.explanation
    assert db.scalar(select(Finding)) is None
    scope = db.scalar(select(ControlAssetScope).where(ControlAssetScope.control_id == "CTRL-IAM-001"))
    assert scope.current_status == "Effective" and scope.latest_assessment_id == a.id
    assert run.summary["results"]["Effective"] == 1


# --------------------------------------------------------------------------- failed MFA
def test_failed_mfa_creates_scored_finding(db, world):
    f.ingest(db, "privileged_accounts", "IDP-CORE-001", f.mfa_payload(missing=("admin_002", "svc_payops_admin")))
    run = f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])

    a = _latest(db, "CTRL-IAM-001", "IDP-CORE-001")
    assert a.result == "Ineffective"
    assert a.details["accounts_without_mfa"] == ["admin_002", "svc_payops_admin"]
    assert "2 of 5 privileged accounts do not have MFA enabled" in a.explanation

    finding = db.scalar(select(Finding))
    assert finding is not None and finding.status == "Open"
    assert finding.latest_assessment_id == a.id == finding.first_assessment_id
    assert a.finding_id == finding.id
    # IDP-CORE-001 is a transitive dependency of both Tier 1 services.
    assert set(finding.impacted_service_ids) == {"SVC-PAY", "SVC-OLB"}
    assert "potential exposure" in finding.business_impact.lower()
    assert 0 <= finding.risk_score <= 100
    assert finding.severity == finding.score_breakdown["severity"]
    assert sum(x["contribution"] for x in finding.score_breakdown["factors"]) == pytest.approx(finding.risk_score, abs=0.5)
    assert run.summary["findings_created"] == [finding.ref]
    # Finding is linked to the register risk mapped to this control and service.
    linked = db.scalars(select(RiskFindingMapping.risk_id).where(RiskFindingMapping.finding_id == finding.id)).all()
    assert linked == ["RSK-001"]


# --------------------------------------------------------------------------- missing evidence
def test_missing_evidence_results_in_needs_review_not_failure(db, world):
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-BCP-001"])
    a = _latest(db, "CTRL-BCP-001", "DB-TXN-001")
    assert a.result == "Needs Review"
    assert a.details["evidence_issue"] == "missing"
    assert a.evidence == []
    assert db.scalar(select(Finding)) is None


def test_missing_evidence_policy_can_be_explicitly_configured():
    rule = get_rule("backup_recovery_test")
    params = rule.parameters({"missing_evidence_result": "Ineffective"})
    out = evaluate_scope(rule, params, {"asset_id": "DB-1"}, None, utcnow())
    assert out.result == "Ineffective"


# --------------------------------------------------------------------------- stale evidence
def test_stale_evidence_results_in_needs_review(db, world):
    old = utcnow() - timedelta(days=10)
    f.ingest(db, "privileged_accounts", "IDP-CORE-001", f.mfa_payload(missing=("admin_x",)), collected_at=old)
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
    a = _latest(db, "CTRL-IAM-001", "IDP-CORE-001")
    # Even though the stale evidence shows a failure, the engine does not conclude on stale data.
    assert a.result == "Needs Review"
    assert a.details["evidence_issue"] == "stale"
    assert a.details["max_age_days"] == 7
    assert db.scalar(select(Finding)) is None


def test_stale_policy_override_and_invalid_policy_value_fall_back_safely():
    rule = get_rule("privileged_mfa")
    stale = _evidence_input("privileged_accounts", f.mfa_payload(), utcnow() - timedelta(days=30))
    assert evaluate_scope(rule, rule.parameters({"stale_evidence_result": "Ineffective"}),
                          {"asset_id": "IDP-CORE-001"}, stale, utcnow()).result == "Ineffective"
    # Effective is never an allowed policy result for stale evidence.
    assert evaluate_scope(rule, rule.parameters({"stale_evidence_result": "Effective"}),
                          {"asset_id": "IDP-CORE-001"}, stale, utcnow()).result == "Needs Review"


def test_invalid_and_mismatched_evidence_need_review():
    rule = get_rule("privileged_mfa")
    now = utcnow()
    invalid = _evidence_input("privileged_accounts", {"asset_id": "IDP-CORE-001"}, now, status="Invalid")
    assert evaluate_scope(rule, rule.parameters(), {"asset_id": "IDP-CORE-001"}, invalid, now).result == "Needs Review"
    other = _evidence_input("privileged_accounts", f.mfa_payload(asset_id="OTHER-001"), now)
    out = evaluate_scope(rule, rule.parameters(), {"asset_id": "IDP-CORE-001"}, other, now)
    assert out.result == "Needs Review" and out.details["evidence_issue"] == "asset_mismatch"


# --------------------------------------------------------------------------- vulnerability SLA
def test_critical_vulnerability_sla_breach(db, world):
    now = utcnow()
    f.ingest(db, "vulnerability_scan", "WEB-BANK-001", f.vuln_payload("WEB-BANK-001", [
        ("SYNTH-1", "Critical", now - timedelta(days=41), True),
        ("SYNTH-2", "Critical", now - timedelta(days=5), False),
        ("SYNTH-3", "High", now - timedelta(days=60), False),
    ]))
    f.ingest(db, "vulnerability_scan", "PAY-API-001", f.vuln_payload("PAY-API-001", [
        ("SYNTH-4", "Critical", now - timedelta(days=10), False),
    ]))
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-VM-001"])

    breach = _latest(db, "CTRL-VM-001", "WEB-BANK-001")
    assert breach.result == "Ineffective"
    assert [b["vuln_id"] for b in breach.details["breaches"]] == ["SYNTH-1"]
    assert breach.details["breaches"][0]["days_over_sla"] == 26
    assert breach.details["exploit_signal"] is True

    within = _latest(db, "CTRL-VM-001", "PAY-API-001")
    assert within.result == "Effective"

    finding = db.scalar(select(Finding).where(Finding.asset_id == "WEB-BANK-001"))
    exposure = next(x for x in finding.score_breakdown["factors"] if x["key"] == "exposure")
    assert exposure["value"] == 1.0  # internet-facing, capped at 1.0 even with known-exploited uplift
    assert exposure["inputs"]["known_exploited"] is True


def test_internet_exposure_rule_not_applicable_to_internal_assets():
    rule = get_rule("internet_vuln_exposure")
    now = utcnow()
    ev = _evidence_input("vulnerability_scan", f.vuln_payload("PAY-API-001", [("V", "Critical", now - timedelta(days=30), False)]), now)
    out = evaluate_scope(rule, rule.parameters(), {"asset_id": "PAY-API-001", "internet_exposed": False}, ev, now)
    assert out.result == "Not Assessed"


# --------------------------------------------------------------------------- backup
def test_overdue_backup_recovery_test_is_ineffective(db, world):
    now = utcnow()
    f.ingest(db, "backup_recovery", "DB-TXN-001", f.backup_payload("DB-TXN-001", now - timedelta(days=241)))
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-BCP-001"])
    a = _latest(db, "CTRL-BCP-001", "DB-TXN-001")
    assert a.result == "Ineffective"
    assert "241" in a.explanation


# --------------------------------------------------------------------------- reproducibility
def test_input_hash_is_deterministic_and_sensitive_to_inputs():
    rule = get_rule("privileged_mfa")
    now = utcnow()
    ev = _evidence_input("privileged_accounts", f.mfa_payload(), now)
    ctx = {"asset_id": "IDP-CORE-001"}
    h1 = compute_input_hash(rule, rule.parameters(), ctx, ev, now)
    assert h1 == compute_input_hash(rule, rule.parameters(), ctx, ev, now)
    assert h1 != compute_input_hash(rule, rule.parameters({"evidence_max_age_days": 3}), ctx, ev, now)
    assert h1 != compute_input_hash(rule, rule.parameters(), ctx, ev, now + timedelta(seconds=1))
