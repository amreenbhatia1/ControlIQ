"""Deterministic evidence payload generators.

Each generator returns the evidence a collector would have produced on a given day (relative to the
seed anchor). Scenario behaviour is encoded explicitly so historical assessments are produced by the
real assessment engine rather than fabricated.
"""

import hashlib
from datetime import datetime, timedelta

from app.core.time import iso


def _rng(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


class Clock:
    def __init__(self, anchor: datetime):
        self.anchor = anchor

    def at(self, day: float) -> datetime:
        return self.anchor + timedelta(days=day)

    def iso(self, day: float) -> str:
        return iso(self.at(day))


# --------------------------------------------------------------------------- privileged accounts
PRIVILEGED_ACCOUNTS = {
    "IDP-CORE-001": [
        ("admin_001", "Global Administrator"),
        ("admin_002", "Global Administrator"),
        ("admin_003", "Application Administrator"),
        ("svc_payops_admin", "Payments Platform Administrator"),
        ("breakglass_01", "Emergency Access"),
        ("idp_ops_lead", "Identity Operations Lead"),
    ],
    "IDP-AD-001": [
        ("ad_admin_ops01", "Domain Administrator"),
        ("ad_admin_ops02", "Domain Administrator"),
        ("ad_admin_legacy07", "Enterprise Administrator"),
        ("ad_tier0_svc", "Tier 0 Service Administrator"),
        ("ad_breakglass", "Emergency Access"),
    ],
    "PAM-VAULT-001": [
        ("pam_admin_01", "Vault Administrator"),
        ("pam_admin_02", "Vault Administrator"),
        ("pam_auditor_01", "Vault Auditor"),
        ("pam_legacy_admin", "Vault Administrator"),
    ],
    "IDP-CIAM-001": [
        ("ciam_admin_01", "Tenant Administrator"),
        ("ciam_admin_02", "Tenant Administrator"),
        ("ciam_policy_admin", "Policy Administrator"),
        ("ciam_breakglass", "Emergency Access"),
        ("ciam_support_lead", "Support Administrator"),
    ],
}
SYSTEM_NAMES = {
    "IDP-CORE-001": "Enterprise Identity Provider",
    "IDP-AD-001": "Corporate Directory Services",
    "PAM-VAULT-001": "Privileged Access Vault",
    "IDP-CIAM-001": "Customer Identity & Access Platform",
}

MFA_SCENARIO_ACCOUNTS = ("admin_002", "svc_payops_admin")


def privileged_accounts(asset_id: str, day: float, clock: Clock, mfa_disabled: tuple[str, ...] = ()) -> dict:
    disabled = set(mfa_disabled)
    if asset_id == "IDP-AD-001" and -62 <= day < -48:
        disabled.add("ad_admin_legacy07")
    accounts = []
    for acct, role in PRIVILEGED_ACCOUNTS[asset_id]:
        status = "disabled" if acct == "pam_legacy_admin" else "active"
        mfa = acct not in disabled and status == "active"
        accounts.append(
            {
                "account_id": acct,
                "role": role,
                "account_status": status,
                "mfa_enabled": mfa,
                "mfa_method": "FIDO2 security key" if mfa else None,
            }
        )
    return {
        "asset_id": asset_id,
        "system": SYSTEM_NAMES[asset_id],
        "export_type": "privileged_account_inventory",
        "privileged_accounts": accounts,
    }


# --------------------------------------------------------------------------- access reviews
REVIEWERS = {
    "PAY-API-001": ("Laura Bennett", 11),
    "TRD-APP-001": ("Hannah Lowe", None),
    "DB-CUST-001": ("Martin Hughes", 37),
    "LOAN-APP-001": ("Rachel Ford", 52),
    "CARD-APP-001": ("Victor Mensah", 23),
    "TRE-APP-001": ("Ian Doyle", 64),
}


def access_review(asset_id: str, day: float, clock: Clock) -> dict:
    reviewer, phase = REVIEWERS[asset_id]
    if phase is None:
        last = -131.0  # Trading review campaign stalled: last completed 131 days before anchor.
    else:
        last = day - ((day - phase) % 75)
    seed = _rng(asset_id, int(last))
    return {
        "asset_id": asset_id,
        "review_id": f"AR-{asset_id[:3]}-{abs(int(last)):03d}",
        "last_review_completed_at": clock.iso(last),
        "reviewer": reviewer,
        "accounts_reviewed": 18 + seed % 30,
        "accounts_revoked": seed % 4,
    }


# --------------------------------------------------------------------------- vulnerabilities
# (vuln_id, synthetic_id, title, severity, detected_day, resolved_day, known_exploited)
SCENARIO_VULNS = {
    "WEB-BANK-001": [
        ("V-WEB-0412", "SYNTH-2026-0412", "Template injection leading to remote code execution in web framework", "Critical", -41, None, True),
        ("V-WEB-0388", "SYNTH-2026-0388", "Session fixation in authentication middleware", "High", -20, None, False),
    ],
    "LOAN-APP-001": [
        ("V-LOAN-0455", "SYNTH-2026-0455", "Unsafe deserialisation in document processing library", "Critical", -22, None, False),
    ],
    "MOB-API-001": [
        ("V-MOB-0471", "SYNTH-2026-0471", "Broken object-level authorisation on account endpoint", "High", -12, None, False),
    ],
    "PAY-API-001": [
        ("V-PAY-0207", "SYNTH-2026-0207", "Heap overflow in TLS termination library", "Critical", -96, -66, True),
    ],
    "CARD-AUTH-001": [
        ("V-CARD-0301", "SYNTH-2026-0301", "Privilege escalation in host management agent", "Critical", -55, -31, False),
    ],
    "FRD-ENG-001": [
        ("V-FRD-0350", "SYNTH-2026-0350", "Remote code execution in stream processing connector", "Critical", -40, -16, False),
    ],
    "LOAN-PORTAL-001": [
        ("V-LNP-0260", "SYNTH-2026-0260", "Stored cross-site scripting in application upload form", "High", -58, -38, False),
    ],
    "WLT-PORTAL-001": [
        ("V-WLT-0333", "SYNTH-2026-0333", "Server-side request forgery in report export", "High", -28, -12, False),
    ],
}

BACKGROUND_TITLES = [
    ("Medium", "Outdated TLS cipher suites permitted"),
    ("Low", "Verbose server banner discloses version"),
    ("Medium", "Missing HTTP security headers"),
    ("Low", "Self-signed certificate on management interface"),
    ("Medium", "Weak SSH key exchange algorithms enabled"),
]


def vulnerability_scan(asset_id: str, day: float, clock: Clock) -> dict:
    vulns = []
    seed = _rng(asset_id)
    for i in range(2 + seed % 2):
        sev, title = BACKGROUND_TITLES[(seed + i) % len(BACKGROUND_TITLES)]
        vulns.append(
            {
                "vuln_id": f"V-{asset_id[:4]}-B{i + 1:02d}",
                "cve_id": None,
                "title": title,
                "severity": sev,
                "first_detected_at": clock.iso(-120 - 30 * i),
                "status": "Open",
                "known_exploited": False,
            }
        )
    for vid, syn, title, sev, detected, resolved, kev in SCENARIO_VULNS.get(asset_id, []):
        if detected > day:
            continue
        status = "Resolved" if resolved is not None and day >= resolved else "Open"
        vulns.append(
            {
                "vuln_id": vid,
                "cve_id": syn,
                "title": title,
                "severity": sev,
                "first_detected_at": clock.iso(detected),
                "status": status,
                "known_exploited": kev,
            }
        )
    return {
        "asset_id": asset_id,
        "scanner": "Authenticated vulnerability scanner (synthetic)",
        "scan_completed_at": clock.iso(day - 0.1),
        "vulnerabilities": vulns,
    }


# --------------------------------------------------------------------------- logging
def logging_coverage(asset_id: str, day: float, clock: Clock) -> dict:
    seed = _rng(asset_id, int(day))
    sources = []
    for src in ("authentication", "system", "security"):
        last_event = day - (5 + (seed % 40)) / 1440
        active = True
        if asset_id == "DB-TRD-001" and src == "authentication" and day >= -3.2:
            last_event = -3.2
        if asset_id == "DB-CUST-001" and src == "security" and -35 <= day < -30:
            active = False
        if asset_id == "DB-TXN-001" and src == "system" and -45 <= day < -42:
            continue  # source dropped from SIEM during log pipeline migration
        sources.append({"source_type": src, "active": active, "last_event_at": clock.iso(last_event)})
    return {"asset_id": asset_id, "siem_platform": "SIEM-001", "log_sources": sources}


# --------------------------------------------------------------------------- endpoint
def endpoint_protection(asset_id: str, day: float, clock: Clock) -> dict | None:
    if asset_id == "LOAN-SRV-001" and day > -9:
        return None  # collector stopped reporting -> evidence becomes stale
    status = "healthy"
    check_in = day - 0.02
    signature = day - 0.25
    if asset_id == "TRD-SRV-003" and day >= -9:
        status, check_in = "offline", -9.5
    if asset_id == "PAY-SRV-004" and -55 <= day < -50:
        status = "degraded"
    if asset_id == "TRD-SRV-001" and -15 <= day < -12:
        signature = -24
    return {
        "asset_id": asset_id,
        "edr_product": "EDR agent (synthetic)",
        "agent_installed": True,
        "agent_status": status,
        "signature_updated_at": clock.iso(signature),
        "last_check_in_at": clock.iso(check_in),
    }


# --------------------------------------------------------------------------- backup recovery
RECOVERY_TESTS = {
    "DB-TXN-001": [("RT-TXN-0198", -241, "passed", True), ("RT-TXN-0231", -120, "partial", False)],
    "DB-CARD-001": [("RT-CARD-0140", -275, "passed", True), ("RT-CARD-0187", -75, "passed", True)],
    "DB-CUST-001": [("RT-CUST-0166", -150, "passed", True), ("RT-CUST-0212", -40, "passed", True)],
    "DB-TRD-001": [("RT-TRD-0158", -100, "passed", True), ("RT-TRD-0240", -10, "passed", True)],
}


def backup_recovery(asset_id: str, day: float, clock: Clock) -> dict | None:
    tests = RECOVERY_TESTS.get(asset_id)
    if tests is None:
        return None  # DB-LOAN-001: no recovery evidence has ever been submitted
    return {
        "asset_id": asset_id,
        "backup_policy": "Daily immutable snapshot, 35-day retention, cross-region copy",
        "recovery_tests": [
            {"test_id": tid, "performed_at": clock.iso(d), "result": result, "rto_met": rto}
            for tid, d, result, rto in tests
            if d <= day
        ],
    }


# --------------------------------------------------------------------------- change records
def change_records(asset_id: str, day: float, clock: Clock) -> dict:
    short = asset_id.split("-")[0]
    changes = []
    seed = _rng(asset_id)
    d = -130 + seed % 3
    n = 1
    while d <= day:
        if day - 30 < d:
            changes.append(
                {
                    "change_id": f"CHG-{short}-{1000 + n}",
                    "deployed_at": clock.iso(d + 0.4),
                    "environment": "Production",
                    "approval_id": f"CAB-{4000 + n + seed % 500}",
                    "emergency": False,
                    "retrospective_approval_id": None,
                }
            )
        d += 3 + (n % 2)
        n += 1
    if asset_id == "CARD-APP-001":
        for cid, dd in (("CHG-CARD-7781", -16), ("CHG-CARD-7794", -9)):
            if day - 30 < dd <= day:
                changes.append(
                    {"change_id": cid, "deployed_at": clock.iso(dd + 0.6), "environment": "Production",
                     "approval_id": None, "emergency": False, "retrospective_approval_id": None}
                )
    if asset_id == "PAY-API-001" and day - 30 < -71 <= day:
        changes.append(
            {"change_id": "CHG-PAY-6620", "deployed_at": clock.iso(-71 + 0.1), "environment": "Production",
             "approval_id": None, "emergency": True,
             "retrospective_approval_id": "CAB-R-0912" if day >= -60 else None}
        )
    changes.sort(key=lambda c: c["deployed_at"])
    return {
        "asset_id": asset_id,
        "period_start": clock.iso(day - 30),
        "period_end": clock.iso(day),
        "changes": changes,
    }


# --------------------------------------------------------------------------- encryption
def encryption_status(asset_id: str, day: float, clock: Clock) -> dict:
    count = 4 + _rng(asset_id) % 3
    vols = [
        {"volume_id": f"{asset_id.lower()}-vol-{i + 1:02d}", "encrypted": True, "key_management": "Central KMS (HSM-backed)"}
        for i in range(count)
    ]
    if asset_id == "DWH-001":
        vols.append({"volume_id": "dwh-archive-vol-legacy", "encrypted": False, "key_management": "none"})
    return {"asset_id": asset_id, "storage_volumes": vols}


# --------------------------------------------------------------------------- third parties
VENDORS = {
    "EXT-PAYNET-001": ("ClearRail Interbank Network", "Tier 1", lambda d: -200, 0),
    "EXT-KYC-001": ("VeriPass Identity", "Tier 1", lambda d: -412, 2),
    "EXT-MKTDATA-001": ("Northwind Market Data", "Tier 1", lambda d: -460 if d < -57 else -57, 1),
    "EXT-CREDIT-001": ("Crestline Credit Bureau", "Tier 2", lambda d: -300, 0),
    "CLOUD-CRM-001": ("Harbourline CRM", "Tier 3", lambda d: -500, 1),
}


def third_party_assessment(asset_id: str, day: float, clock: Clock) -> dict:
    vendor, tier, last_fn, issues = VENDORS[asset_id]
    return {
        "asset_id": asset_id,
        "vendor_name": vendor,
        "risk_tier": tier,
        "last_assessment_completed_at": clock.iso(last_fn(day)),
        "assessment_type": "Security questionnaire + independent assurance report review",
        "open_high_issues": issues,
    }


GENERATORS = {
    "privileged_accounts": privileged_accounts,
    "access_review": access_review,
    "vulnerability_scan": vulnerability_scan,
    "logging_coverage": logging_coverage,
    "endpoint_protection": endpoint_protection,
    "backup_recovery": backup_recovery,
    "change_records": change_records,
    "encryption_status": encryption_status,
    "third_party_assessment": third_party_assessment,
}

SOURCES = {
    "privileged_accounts": "Identity governance export (synthetic connector)",
    "access_review": "Access certification platform",
    "vulnerability_scan": "Authenticated vulnerability scanner",
    "logging_coverage": "SIEM-001 coverage report",
    "endpoint_protection": "EDR management console",
    "backup_recovery": "Backup orchestration platform",
    "change_records": "ITSM change reconciliation",
    "encryption_status": "Storage configuration inventory",
    "third_party_assessment": "Supplier risk management platform",
}
