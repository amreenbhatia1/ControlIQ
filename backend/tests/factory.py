"""Builders for a compact synthetic environment used by the test suite."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.controls.rules import get_rule
from app.core.time import utcnow
from app.models import (
    Asset,
    AssetDependency,
    BusinessService,
    Control,
    ControlAssetScope,
    Risk,
    RiskControlMapping,
    RiskServiceMapping,
    User,
)
from app.seed import data
from app.seed.seeder import ensure_roles_and_users
from app.services import settings_service
from app.services.assessment_service import run_assessment
from app.services.evidence_service import ingest_evidence

ADMIN = "alex.morgan@alphabetabank.example"
ANALYST = "priya.raman@alphabetabank.example"
IAM_OWNER = "daniel.okafor@alphabetabank.example"
VM_OWNER = "marcus.chen@alphabetabank.example"
EXECUTIVE = "catherine.hale@alphabetabank.example"

SERVICES = [
    ("SVC-PAY", "Payment Processing", "Tier 1"),
    ("SVC-OLB", "Online Banking", "Tier 1"),
    ("SVC-WLT", "Wealth Management", "Tier 2"),
]

# id, name, type, criticality, internet, privileged hub, redundancy
ASSETS = [
    ("IDP-CORE-001", "Enterprise Identity Provider", "Identity Service", "Critical", False, True, False),
    ("PAY-API-001", "Payments API", "Application", "Critical", False, False, True),
    ("DB-TXN-001", "Payment Transaction Database", "Database", "Critical", False, False, True),
    ("WEB-BANK-001", "Online Banking Frontend", "Application", "Critical", True, False, True),
    ("WLT-APP-001", "Wealth Portfolio Application", "Application", "Medium", False, False, False),
    ("LAB-SRV-001", "Isolated Lab Server", "Server", "Low", False, False, False),
]

# (asset, depends on)
DEPENDENCIES = [
    ("PAY-API-001", "IDP-CORE-001"),
    ("PAY-API-001", "DB-TXN-001"),
    ("WEB-BANK-001", "IDP-CORE-001"),
    ("WEB-BANK-001", "PAY-API-001"),
]

SERVICE_LINKS = {"SVC-PAY": ["PAY-API-001"], "SVC-OLB": ["WEB-BANK-001"], "SVC-WLT": ["WLT-APP-001"]}

SCOPES = {
    "CTRL-IAM-001": ["IDP-CORE-001"],
    "CTRL-VM-001": ["WEB-BANK-001", "PAY-API-001"],
    "CTRL-VM-002": ["WEB-BANK-001"],
    "CTRL-LOG-001": ["IDP-CORE-001"],
    "CTRL-BCP-001": ["DB-TXN-001"],
}


@dataclass
class World:
    users: dict[str, User]

    def user(self, email: str) -> User:
        return self.users[email]


def build_world(db: Session) -> World:
    users = ensure_roles_and_users(db)
    settings_service.ensure_defaults(db)
    for sid, name, tier in SERVICES:
        db.add(BusinessService(id=sid, name=name, tier=tier, business_owner="Test Owner"))
    created = utcnow() - timedelta(days=200)
    for aid, name, atype, crit, internet, priv, red in ASSETS:
        db.add(
            Asset(id=aid, name=name, asset_type=atype, criticality=crit, internet_exposed=internet,
                  privileged_access_hub=priv, has_redundancy=red, business_owner="Test", technical_owner="Test",
                  created_at=created, updated_at=created)
        )
    db.flush()
    for a, b in DEPENDENCIES:
        db.add(AssetDependency(asset_id=a, depends_on_asset_id=b))
    from app.models import ServiceAssetDependency

    for sid, assets in SERVICE_LINKS.items():
        for aid in assets:
            db.add(ServiceAssetDependency(service_id=sid, asset_id=aid))
    specs = {c["id"]: c for c in data.CONTROLS}
    for cid, scopes in SCOPES.items():
        spec = specs[cid]
        rule = get_rule(spec["rule_key"])
        db.add(
            Control(id=cid, name=spec["name"], description=spec["description"], domain=spec["domain"],
                    objective=spec["objective"], risk_addressed=spec["risk_addressed"],
                    owner_id=users[spec["owner"]].id, frequency=spec["frequency"], rule_key=spec["rule_key"],
                    rule_parameters=dict(spec["parameters"]), evaluation_rule=rule.summary,
                    evidence_category=rule.evidence_category, required_evidence=spec["required_evidence"],
                    failure_severity=spec["failure_severity"], current_status="Not Assessed")
        )
        db.flush()
        for aid in scopes:
            db.add(ControlAssetScope(control_id=cid, asset_id=aid))
    db.add(Risk(id="RSK-001", title="Privileged credential compromise", description="Test risk",
                category="Cyber Security", owner_id=users[ANALYST].id, inherent_rating="Critical",
                residual_rating="High", treatment="Mitigate", treatment_plan="Enforce MFA",
                review_date=utcnow() + timedelta(days=90)))
    db.flush()
    db.add(RiskControlMapping(risk_id="RSK-001", control_id="CTRL-IAM-001"))
    db.add(RiskServiceMapping(risk_id="RSK-001", service_id="SVC-PAY"))
    db.commit()
    return World(users=users)


# ----------------------------------------------------------------------------- evidence payloads
def mfa_payload(asset_id: str = "IDP-CORE-001", missing: tuple[str, ...] = (), extra_active: int = 3) -> dict:
    accounts = [{"account_id": f"admin_{i:03d}", "mfa_enabled": True, "role": "Domain Admin"} for i in range(extra_active)]
    accounts += [{"account_id": a, "mfa_enabled": False, "role": "Service Admin"} for a in missing]
    return {"asset_id": asset_id, "privileged_accounts": accounts}


def vuln_payload(asset_id: str, vulns: list[tuple[str, str, datetime, bool]]) -> dict:
    return {
        "asset_id": asset_id,
        "scanner": "Synthetic scanner",
        "vulnerabilities": [
            {"vuln_id": vid, "cve_id": None, "title": f"Synthetic issue {vid}", "severity": sev,
             "first_detected_at": detected.isoformat(), "status": "Open", "known_exploited": kev}
            for vid, sev, detected, kev in vulns
        ],
    }


def backup_payload(asset_id: str, last_test: datetime, result: str = "passed") -> dict:
    return {
        "asset_id": asset_id,
        "backup_policy": "Daily incremental",
        "recovery_tests": [{"test_id": "RT-1", "performed_at": last_test.isoformat(), "result": result, "rto_met": True}],
    }


def logging_payload(asset_id: str, now: datetime) -> dict:
    return {
        "asset_id": asset_id,
        "siem_platform": "Synthetic SIEM",
        "log_sources": [
            {"source_type": s, "active": True, "last_event_at": (now - timedelta(minutes=5)).isoformat()}
            for s in ("authentication", "system", "security")
        ],
    }


def ingest(db: Session, category: str, asset_id: str, payload: dict, *, collected_at: datetime | None = None,
           user: User | None = None):
    now = utcnow()
    ev = ingest_evidence(
        db,
        content=json.dumps(payload).encode(),
        filename=f"{category}_{asset_id}.json",
        category=category,
        source="Test connector",
        asset_id=asset_id,
        collected_at=collected_at or now - timedelta(hours=1),
        uploaded_by=user,
        now=now,
    )
    db.commit()
    return ev


def run(db: Session, user: User | None = None, as_of: datetime | None = None, control_ids=None):
    return run_assessment(db, triggered_by=user, trigger="manual", as_of=as_of, control_ids=control_ids)
