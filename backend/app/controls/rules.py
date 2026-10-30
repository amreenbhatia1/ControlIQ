"""Deterministic control evaluation rules.

Every rule receives a validated evidence model, parameters, asset context and the evaluation
timestamp (`as_of`). Rules never read the clock or the database, which makes each result
reproducible from its recorded inputs.
"""

from app.controls.base import EFFECTIVE, INEFFECTIVE, NEEDS_REVIEW, NOT_ASSESSED, ControlRule, RuleOutcome
from app.controls import evidence_schemas as es


def _days(delta) -> float:
    return delta.total_seconds() / 86400


def _fmt_list(items: list[str], limit: int = 5) -> str:
    shown = ", ".join(items[:limit])
    if len(items) > limit:
        shown += f" and {len(items) - limit} more"
    return shown


class PrivilegedMfaRule(ControlRule):
    key = "privileged_mfa"
    version = "1.2.0"
    title = "Privileged MFA enforcement"
    evidence_category = "privileged_accounts"
    default_parameters = {"evidence_max_age_days": 7}
    summary = (
        "Ineffective if any active privileged account in scope has MFA disabled. "
        "Needs Review if the inventory lists no active privileged accounts."
    )
    remediation = (
        "Enforce phishing-resistant MFA on every listed privileged account, revoke standing sessions "
        "for the affected accounts, and submit an updated privileged account export for re-assessment."
    )

    def evaluate(self, evidence: es.PrivilegedAccountsEvidence, params, context, as_of) -> RuleOutcome:
        accounts = [a for a in evidence.privileged_accounts if a.account_status == "active"]
        if not accounts:
            return RuleOutcome(
                NEEDS_REVIEW,
                "The privileged account inventory lists no active privileged accounts. "
                "Scope must be confirmed before effectiveness can be concluded.",
            )
        missing = [a.account_id for a in accounts if not a.mfa_enabled]
        details = {
            "accounts_in_scope": len(accounts),
            "accounts_without_mfa": missing,
            "accounts_with_mfa": len(accounts) - len(missing),
        }
        if missing:
            noun = "account does" if len(missing) == 1 else "accounts do"
            return RuleOutcome(
                INEFFECTIVE,
                f"{len(missing)} of {len(accounts)} privileged {noun} not have MFA enabled "
                f"({_fmt_list(missing)}).",
                details,
                failure_magnitude=len(missing) / len(accounts),
            )
        return RuleOutcome(
            EFFECTIVE, f"All {len(accounts)} active privileged accounts have MFA enabled.", details
        )


class PrivilegedAccessReviewRule(ControlRule):
    key = "privileged_access_review"
    version = "1.0.0"
    title = "Privileged access review completion"
    evidence_category = "access_review"
    default_parameters = {"review_period_days": 90, "evidence_max_age_days": 30}
    summary = "Ineffective if the most recent completed privileged access review is older than the review period."
    remediation = (
        "Complete a privileged access recertification for the application, revoke unjustified entitlements "
        "and upload the signed review record."
    )

    def evaluate(self, evidence: es.AccessReviewEvidence, params, context, as_of) -> RuleOutcome:
        period = int(params["review_period_days"])
        completed = evidence.last_review_completed_at
        if completed is None:
            return RuleOutcome(
                INEFFECTIVE,
                f"No completed privileged access review is recorded; policy requires a review every {period} days.",
                {"review_period_days": period},
                failure_magnitude=1.0,
            )
        age = _days(as_of - completed)
        details = {
            "review_period_days": period,
            "last_review_completed_at": completed.isoformat(),
            "days_since_review": round(age, 1),
            "reviewer": evidence.reviewer,
        }
        if age > period:
            overdue = age - period
            details["days_overdue"] = round(overdue, 1)
            return RuleOutcome(
                INEFFECTIVE,
                f"The last privileged access review was completed {int(age)} days ago, "
                f"{int(overdue)} days beyond the {period}-day review period.",
                details,
                failure_magnitude=min(1.0, overdue / period),
            )
        return RuleOutcome(
            EFFECTIVE,
            f"Privileged access review completed {int(age)} days ago, within the {period}-day review period.",
            details,
        )


class CriticalVulnerabilitySlaRule(ControlRule):
    key = "critical_vuln_sla"
    version = "1.1.0"
    title = "Critical vulnerability remediation SLA"
    evidence_category = "vulnerability_scan"
    default_parameters = {"sla_days": {"Critical": 15}, "evidence_max_age_days": 7}
    summary = "Ineffective if any open vulnerability of an in-scope severity has exceeded its remediation SLA."
    remediation = (
        "Patch or apply vendor mitigation for the breaching vulnerabilities, prioritising any listed as "
        "known-exploited, then provide a fresh authenticated scan."
    )

    def evaluate(self, evidence: es.VulnerabilityScanEvidence, params, context, as_of) -> RuleOutcome:
        sla: dict = params["sla_days"]
        in_scope = [v for v in evidence.vulnerabilities if v.status == "Open" and v.severity in sla]
        breaches = []
        for v in in_scope:
            age = _days(as_of - v.first_detected_at)
            limit = int(sla[v.severity])
            if age > limit:
                breaches.append(
                    {
                        "vuln_id": v.vuln_id,
                        "cve_id": v.cve_id,
                        "title": v.title,
                        "severity": v.severity,
                        "age_days": int(age),
                        "sla_days": limit,
                        "days_over_sla": int(age - limit),
                        "known_exploited": v.known_exploited,
                    }
                )
        breaches.sort(key=lambda b: (-b["days_over_sla"], b["vuln_id"]))
        details = {"open_in_scope": len(in_scope), "sla_days": sla, "breaches": breaches}
        if breaches:
            worst = breaches[0]
            label = worst["cve_id"] or worst["vuln_id"]
            kev = any(b["known_exploited"] for b in breaches)
            return RuleOutcome(
                INEFFECTIVE,
                f"{len(breaches)} open {'/'.join(sla.keys()).lower()} vulnerabilit{'y has' if len(breaches) == 1 else 'ies have'} "
                f"exceeded the remediation SLA. Oldest: {label} open {worst['age_days']} days "
                f"(SLA {worst['sla_days']} days)" + (", flagged as known-exploited." if kev else "."),
                details,
                failure_magnitude=min(1.0, max(b["days_over_sla"] for b in breaches) / 30),
                exploit_signal=kev,
            )
        if in_scope:
            msg = f"{len(in_scope)} open in-scope vulnerabilit{'y is' if len(in_scope) == 1 else 'ies are'} within SLA."
        else:
            msg = "No open vulnerabilities of in-scope severity were reported by the latest scan."
        return RuleOutcome(EFFECTIVE, msg, details)


class InternetFacingExposureRule(ControlRule):
    key = "internet_vuln_exposure"
    version = "1.0.0"
    title = "Internet-facing vulnerability exposure"
    evidence_category = "vulnerability_scan"
    default_parameters = {"severities": ["Critical", "High"], "triage_grace_days": 7, "evidence_max_age_days": 7}
    summary = (
        "Applies to internet-facing assets only. Ineffective if any High or Critical vulnerability "
        "remains open beyond the triage grace period."
    )
    remediation = (
        "Remediate or shield the exposed vulnerabilities (patch, WAF virtual patch or exposure removal) and "
        "provide an updated external scan."
    )

    def evaluate(self, evidence: es.VulnerabilityScanEvidence, params, context, as_of) -> RuleOutcome:
        if not context.get("internet_exposed", False):
            return RuleOutcome(NOT_ASSESSED, "Asset is not internet-facing; this control is not applicable.")
        severities = set(params["severities"])
        grace = int(params["triage_grace_days"])
        exposed = []
        for v in evidence.vulnerabilities:
            if v.status != "Open" or v.severity not in severities:
                continue
            age = _days(as_of - v.first_detected_at)
            if age > grace:
                exposed.append(
                    {
                        "vuln_id": v.vuln_id,
                        "cve_id": v.cve_id,
                        "title": v.title,
                        "severity": v.severity,
                        "age_days": int(age),
                        "known_exploited": v.known_exploited,
                    }
                )
        exposed.sort(key=lambda e: (e["severity"] != "Critical", -e["age_days"], e["vuln_id"]))
        details = {"exposed_vulnerabilities": exposed, "triage_grace_days": grace}
        if exposed:
            crit = sum(1 for e in exposed if e["severity"] == "Critical")
            kev = any(e["known_exploited"] for e in exposed)
            return RuleOutcome(
                INEFFECTIVE,
                f"Internet-facing asset has {len(exposed)} unresolved High/Critical vulnerabilit"
                f"{'y' if len(exposed) == 1 else 'ies'} ({crit} critical) open beyond the {grace}-day triage window"
                + (", including known-exploited issues." if kev else "."),
                details,
                failure_magnitude=min(1.0, 0.5 + 0.25 * crit),
                exploit_signal=kev,
            )
        return RuleOutcome(
            EFFECTIVE, "No High or Critical vulnerabilities remain open beyond the triage window.", details
        )


class SecurityLoggingCoverageRule(ControlRule):
    key = "security_logging_coverage"
    version = "1.0.0"
    title = "Security logging coverage"
    evidence_category = "logging_coverage"
    default_parameters = {
        "required_sources": ["authentication", "system", "security"],
        "max_silence_hours": 24,
        "evidence_max_age_days": 2,
    }
    summary = (
        "Ineffective if any required log source is missing, inactive, or has not delivered events "
        "within the permitted silence window."
    )
    remediation = (
        "Restore log forwarding for the failing sources, confirm SIEM ingestion and parsing, and provide an "
        "updated coverage export."
    )

    def evaluate(self, evidence: es.LoggingCoverageEvidence, params, context, as_of) -> RuleOutcome:
        required = list(params["required_sources"])
        max_silence = float(params["max_silence_hours"])
        by_type = {s.source_type: s for s in evidence.log_sources}
        gaps = []
        for src in required:
            s = by_type.get(src)
            if s is None:
                gaps.append({"source_type": src, "issue": "not onboarded"})
            elif not s.active:
                gaps.append({"source_type": src, "issue": "inactive"})
            elif s.last_event_at is None or (as_of - s.last_event_at).total_seconds() / 3600 > max_silence:
                hours = None if s.last_event_at is None else int((as_of - s.last_event_at).total_seconds() / 3600)
                gaps.append({"source_type": src, "issue": f"silent for {hours} hours" if hours is not None else "no events"})
        details = {"required_sources": required, "gaps": gaps, "max_silence_hours": max_silence}
        if gaps:
            desc = "; ".join(f"{g['source_type']} ({g['issue']})" for g in gaps)
            return RuleOutcome(
                INEFFECTIVE,
                f"{len(gaps)} of {len(required)} required security log sources are not reporting: {desc}.",
                details,
                failure_magnitude=len(gaps) / len(required),
            )
        return RuleOutcome(
            EFFECTIVE, f"All {len(required)} required log sources are active and reporting to the SIEM.", details
        )


class EndpointProtectionRule(ControlRule):
    key = "endpoint_protection"
    version = "1.0.0"
    title = "Endpoint protection coverage"
    evidence_category = "endpoint_protection"
    default_parameters = {"max_signature_age_days": 7, "max_check_in_hours": 72, "evidence_max_age_days": 3}
    summary = (
        "Ineffective if the EDR agent is missing, offline, degraded, or has outdated detection content. "
        "Needs Review if the agent has not checked in recently enough to confirm its state."
    )
    remediation = "Reinstall or repair the endpoint agent, force a content update, and confirm healthy check-in."

    def evaluate(self, evidence: es.EndpointProtectionEvidence, params, context, as_of) -> RuleOutcome:
        details = {"agent_status": evidence.agent_status, "agent_installed": evidence.agent_installed}
        if not evidence.agent_installed or evidence.agent_status == "not_installed":
            return RuleOutcome(INEFFECTIVE, "No endpoint protection agent is installed.", details, 1.0)
        if evidence.agent_status in ("offline", "degraded"):
            return RuleOutcome(
                INEFFECTIVE,
                f"Endpoint protection agent is {evidence.agent_status}.",
                details,
                1.0 if evidence.agent_status == "offline" else 0.6,
            )
        if evidence.last_check_in_at is None:
            return RuleOutcome(NEEDS_REVIEW, "Agent reports healthy but has no recorded check-in time.", details)
        check_in_hours = (as_of - evidence.last_check_in_at).total_seconds() / 3600
        details["hours_since_check_in"] = int(check_in_hours)
        if check_in_hours > float(params["max_check_in_hours"]):
            return RuleOutcome(
                NEEDS_REVIEW,
                f"Agent last checked in {int(check_in_hours)} hours ago (limit {params['max_check_in_hours']}h); "
                "current protection state cannot be confirmed.",
                details,
            )
        if evidence.signature_updated_at is None:
            return RuleOutcome(INEFFECTIVE, "Agent has never received detection content updates.", details, 0.8)
        sig_age = _days(as_of - evidence.signature_updated_at)
        details["signature_age_days"] = round(sig_age, 1)
        if sig_age > float(params["max_signature_age_days"]):
            return RuleOutcome(
                INEFFECTIVE,
                f"Detection content is {int(sig_age)} days old, exceeding the {params['max_signature_age_days']}-day limit.",
                details,
                0.5,
            )
        return RuleOutcome(EFFECTIVE, "Endpoint agent is healthy with current detection content.", details)


class BackupRecoveryTestRule(ControlRule):
    key = "backup_recovery_test"
    version = "1.0.0"
    title = "Backup recovery testing"
    evidence_category = "backup_recovery"
    default_parameters = {"test_period_days": 180, "overdue_result": INEFFECTIVE, "evidence_max_age_days": 30}
    summary = (
        "Requires a successful recovery test within the test period. The overdue outcome is set explicitly by "
        "policy (`overdue_result`) because test currency is the control's pass/fail criterion."
    )
    remediation = (
        "Schedule and execute a full restore test for the system, record achieved RTO/RPO, and upload the "
        "signed test report."
    )

    def evaluate(self, evidence: es.BackupRecoveryEvidence, params, context, as_of) -> RuleOutcome:
        period = int(params["test_period_days"])
        overdue_result = params.get("overdue_result", INEFFECTIVE)
        passed = [t for t in evidence.recovery_tests if t.result == "passed" and t.performed_at <= as_of]
        failed_recent = [
            t.test_id for t in evidence.recovery_tests if t.result != "passed" and _days(as_of - t.performed_at) <= period
        ]
        details = {"test_period_days": period, "recent_unsuccessful_tests": failed_recent}
        if not passed:
            return RuleOutcome(
                overdue_result,
                f"No successful recovery test is recorded; policy requires one every {period} days.",
                details,
                failure_magnitude=1.0,
            )
        latest = max(passed, key=lambda t: t.performed_at)
        age = _days(as_of - latest.performed_at)
        details.update({"last_successful_test": latest.test_id, "days_since_success": int(age)})
        if age > period:
            return RuleOutcome(
                overdue_result,
                f"Last successful recovery test ({latest.test_id}) was {int(age)} days ago, "
                f"beyond the {period}-day testing requirement.",
                details,
                failure_magnitude=min(1.0, (age - period) / period),
            )
        return RuleOutcome(
            EFFECTIVE,
            f"Successful recovery test {latest.test_id} completed {int(age)} days ago (requirement: {period} days).",
            details,
        )


class ProductionChangeApprovalRule(ControlRule):
    key = "production_change_approval"
    version = "1.0.0"
    title = "Production change approval"
    evidence_category = "change_records"
    default_parameters = {"allow_retrospective_emergency_approval": True, "evidence_max_age_days": 35}
    summary = (
        "Ineffective if any production change lacks an approval record. Emergency changes pass only with a "
        "documented retrospective approval when policy permits it."
    )
    remediation = (
        "Raise retrospective approvals or rollback reviews for the unapproved changes, investigate how the "
        "deployment pipeline bypassed the approval gate, and enforce pipeline-level change verification."
    )

    def evaluate(self, evidence: es.ChangeRecordsEvidence, params, context, as_of) -> RuleOutcome:
        allow_retro = bool(params["allow_retrospective_emergency_approval"])
        prod = [c for c in evidence.changes if c.environment.lower() == "production"]
        unapproved = []
        for c in prod:
            if c.approval_id:
                continue
            if c.emergency and allow_retro and c.retrospective_approval_id:
                continue
            unapproved.append(c.change_id)
        details = {"production_changes": len(prod), "unapproved_changes": unapproved}
        if not prod:
            return RuleOutcome(EFFECTIVE, "No production changes were deployed in the reporting period.", details)
        if unapproved:
            return RuleOutcome(
                INEFFECTIVE,
                f"{len(unapproved)} of {len(prod)} production changes have no approval record ({_fmt_list(unapproved)}).",
                details,
                failure_magnitude=min(1.0, len(unapproved) / max(1, len(prod)) * 2),
            )
        return RuleOutcome(EFFECTIVE, f"All {len(prod)} production changes have approval records.", details)


class EncryptionAtRestRule(ControlRule):
    key = "encryption_at_rest"
    version = "1.0.0"
    title = "Data encryption at rest"
    evidence_category = "encryption_status"
    default_parameters = {"evidence_max_age_days": 30}
    summary = "Ineffective if any storage volume holding the asset's data is unencrypted."
    remediation = "Enable encryption with centrally managed keys on the listed volumes and migrate data if required."

    def evaluate(self, evidence: es.EncryptionStatusEvidence, params, context, as_of) -> RuleOutcome:
        vols = evidence.storage_volumes
        if not vols:
            return RuleOutcome(NEEDS_REVIEW, "No storage volumes were reported; scope cannot be confirmed.")
        bad = [v.volume_id for v in vols if not v.encrypted]
        details = {"volumes": len(vols), "unencrypted_volumes": bad}
        if bad:
            return RuleOutcome(
                INEFFECTIVE,
                f"{len(bad)} of {len(vols)} storage volumes are not encrypted at rest ({_fmt_list(bad)}).",
                details,
                failure_magnitude=len(bad) / len(vols),
            )
        return RuleOutcome(EFFECTIVE, f"All {len(vols)} storage volumes are encrypted at rest.", details)


class ThirdPartyAssessmentRule(ControlRule):
    key = "third_party_assessment"
    version = "1.0.0"
    title = "Third-party security assessment currency"
    evidence_category = "third_party_assessment"
    default_parameters = {"reassessment_days": {"Tier 1": 365, "Tier 2": 730, "Tier 3": 1095}, "evidence_max_age_days": 30}
    summary = "Ineffective if the vendor's security assessment has expired for its risk tier."
    remediation = (
        "Initiate a vendor security reassessment, obtain current assurance reports, and track open high issues "
        "through to closure."
    )

    def evaluate(self, evidence: es.ThirdPartyAssessmentEvidence, params, context, as_of) -> RuleOutcome:
        limit = int(params["reassessment_days"][evidence.risk_tier])
        details = {"vendor": evidence.vendor_name, "risk_tier": evidence.risk_tier, "reassessment_days": limit}
        if evidence.last_assessment_completed_at is None:
            return RuleOutcome(
                INEFFECTIVE, f"No security assessment is recorded for {evidence.vendor_name}.", details, 1.0
            )
        age = _days(as_of - evidence.last_assessment_completed_at)
        details["days_since_assessment"] = int(age)
        details["open_high_issues"] = evidence.open_high_issues
        if age > limit:
            return RuleOutcome(
                INEFFECTIVE,
                f"Security assessment of {evidence.vendor_name} is {int(age)} days old; "
                f"{evidence.risk_tier} vendors require reassessment every {limit} days.",
                details,
                failure_magnitude=min(1.0, (age - limit) / 180),
            )
        return RuleOutcome(
            EFFECTIVE,
            f"{evidence.vendor_name} was assessed {int(age)} days ago (requirement: {limit} days).",
            details,
        )


RULES: dict[str, ControlRule] = {
    r.key: r
    for r in (
        PrivilegedMfaRule(),
        PrivilegedAccessReviewRule(),
        CriticalVulnerabilitySlaRule(),
        InternetFacingExposureRule(),
        SecurityLoggingCoverageRule(),
        EndpointProtectionRule(),
        BackupRecoveryTestRule(),
        ProductionChangeApprovalRule(),
        EncryptionAtRestRule(),
        ThirdPartyAssessmentRule(),
    )
}


def get_rule(key: str) -> ControlRule:
    try:
        return RULES[key]
    except KeyError as exc:
        raise KeyError(f"No assessment rule registered for '{key}'") from exc
