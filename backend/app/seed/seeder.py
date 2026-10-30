"""Deterministic seeding of the Alpha Beta Bank synthetic environment."""

import json
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.controls.rules import get_rule
from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.permissions import ROLE_DEFINITIONS
from app.core.security import hash_password
from app.core.time import utcnow
from app.models import (
    Asset,
    AssetDependency,
    BusinessService,
    Control,
    ControlAssetScope,
    Finding,
    RemediationAction,
    RemediationActivity,
    Risk,
    RiskControlMapping,
    RiskServiceMapping,
    Role,
    ServiceAssetDependency,
    User,
)
from app.seed import data
from app.seed.evidence_generators import GENERATORS, SOURCES, Clock
from app.services import settings_service
from app.services.assessment_service import run_assessment
from app.services.evidence_service import ingest_evidence, storage_root
from app.services.graph_service import load_graph

RUN_DAYS = list(range(-90, -7, 3)) + list(range(-7, 1))

DOMAIN_TABLES = [
    "assessment_evidence",
    "remediation_activity",
    "remediation_actions",
    "risk_finding_mappings",
    "risk_control_mappings",
    "risk_service_mappings",
    "risks",
    "control_asset_scopes",
    "findings",
    "control_assessments",
    "assessment_runs",
    "evidence",
    "controls",
    "service_asset_dependencies",
    "asset_dependencies",
    "assets",
    "business_services",
    "generated_reports",
    "app_settings",
]

EXTRA_ASSETS = [
    ("TRD-LEG-MW-001", "Legacy Trading Middleware", "Server", "High", False, False, False, "Solaris 11 / legacy message bus", "Markets", "Markets Technology", "End-of-life middleware scheduled for decommissioning.", "Decommissioning"),
    ("CLD-KMS-001", "Cloud Key Management Service", "Cloud Resource", "Critical", False, False, True, "Managed KMS", "Infrastructure", "Cryptography Services", "Central key management for cloud workloads.", "Active"),
    ("CLD-OBJ-001", "Identity Document Storage", "Cloud Resource", "High", False, False, True, "Object storage (encrypted)", "Customer Identity Services", "Identity Engineering", "Customer onboarding document store.", "Active"),
    ("CLD-ANL-001", "Analytics Sandbox", "Cloud Resource", "Low", False, False, False, "Managed notebooks", "Chief Data Office", "Data Platform Engineering", "Non-production analytics workspace.", "Active"),
    ("NET-VPN-001", "Remote Access VPN Gateway", "Network Device", "High", True, False, True, "SSL VPN HA pair", "Infrastructure", "Network Security", "Workforce remote access.", "Active"),
    ("NET-DDOS-001", "DDoS Mitigation Service", "Cloud Resource", "High", True, False, True, "Managed scrubbing service", "Infrastructure", "Network Security", "Volumetric attack protection.", "Active"),
    ("EXT-SMS-001", "Kestrel SMS OTP Gateway", "Third-Party Integration", "High", False, False, False, "External SMS API", "Customer Identity Services", "Supplier Risk", "Fictional one-time passcode delivery provider.", "Active"),
    ("MAIL-GW-001", "Secure Email Gateway", "Application", "Medium", True, False, True, "Email security appliance", "Infrastructure", "Messaging Engineering", "Inbound and outbound email filtering.", "Active"),
    ("ITSM-001", "IT Service Management Platform", "Application", "Medium", False, False, True, "SaaS ITSM", "Service Management", "Aisha Patel", "Change, incident and problem records.", "Active"),
    ("CI-PIPE-001", "Production Deployment Pipeline", "Application", "High", False, True, True, "CI/CD orchestrator", "Technology Controls Office", "Platform Engineering", "Build and deployment automation with production credentials.", "Active"),
    ("MON-APM-001", "Application Performance Monitoring", "Cloud Resource", "Medium", False, False, True, "SaaS APM", "Infrastructure", "Site Reliability Engineering", "Service telemetry and alerting.", "Planned"),
]
EXTRA_DEPENDENCIES = [
    ("TRD-OMS-001", "TRD-LEG-MW-001"),
    ("KYC-SVC-001", "CLD-OBJ-001"),
    ("IDP-CIAM-001", "EXT-SMS-001"),
    ("DB-CARD-001", "CLD-KMS-001"),
]


def log_default(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- purge
def purge_domain_data(db: Session) -> None:
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text("SET LOCAL controliq.allow_purge = 'on'"))
        db.execute(text("TRUNCATE " + ", ".join(DOMAIN_TABLES) + " RESTART IDENTITY CASCADE"))
    else:
        db.execute(text("PRAGMA foreign_keys=OFF"))
        for t in DOMAIN_TABLES:
            db.execute(text(f"DELETE FROM {t}"))
        db.execute(text("PRAGMA foreign_keys=ON"))
    db.commit()
    root = storage_root()
    for f in root.iterdir():
        if f.is_file() and f.suffix in (".json", ".csv", ".pdf", ".txt"):
            f.unlink(missing_ok=True)


# --------------------------------------------------------------------------- identity
def ensure_roles_and_users(db: Session) -> dict[str, User]:
    roles = {}
    for key, spec in ROLE_DEFINITIONS.items():
        role = db.scalar(select(Role).where(Role.key == key))
        if role is None:
            role = Role(key=key, name=spec["name"], description=spec["description"], permissions=spec["permissions"])
            db.add(role)
        else:
            role.name, role.description, role.permissions = spec["name"], spec["description"], spec["permissions"]
        roles[key] = role
    db.flush()
    pw_hash = hash_password(get_settings().demo_password)
    users = {}
    for email, name, title, team, role_key in data.USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=name, title=title, team=team, role_id=roles[role_key].id,
                        password_hash=pw_hash, can_login=True, is_active=True)
            db.add(user)
        else:
            user.full_name, user.title, user.team, user.role_id = name, title, team, roles[role_key].id
            user.is_active = True
            user.can_login = True
        users[email] = user
    db.flush()
    return users


# --------------------------------------------------------------------------- inventory
def build_inventory(db: Session, created_at: datetime) -> None:
    for sid, name, tier, owner, cf, rto, vol, desc in data.SERVICES:
        db.add(BusinessService(id=sid, name=name, tier=tier, business_owner=owner, customer_facing=cf,
                               rto_hours=rto, daily_transaction_volume=vol, description=desc))

    def add_asset(aid, name, atype, crit, internet, priv, redundancy, platform, bo, to, desc,
                  env="Production", lifecycle="Active"):
        db.add(Asset(id=aid, name=name, asset_type=atype, criticality=crit, internet_exposed=internet,
                     privileged_access_hub=priv, has_redundancy=redundancy, platform=platform,
                     business_owner=bo, technical_owner=to, description=desc, environment=env,
                     lifecycle_status=lifecycle, created_at=created_at, updated_at=created_at))

    for row in data.CORE_ASSETS:
        add_asset(*row)
    for row in EXTRA_ASSETS:
        *base, lifecycle = row
        add_asset(*base, env="Development" if base[0] == "CLD-ANL-001" else "Production", lifecycle=lifecycle)

    core = {row[0]: row for row in data.CORE_ASSETS}
    counters: dict[str, int] = {}
    host_edges = []
    for app_id, prefix, count, platform in data.HOSTS:
        app = core[app_id]
        for _ in range(count):
            counters[prefix] = counters.get(prefix, 0) + 1
            hid = f"{prefix}-SRV-{counters[prefix]:03d}"
            crit = "High" if app[3] == "Critical" else "Medium"
            add_asset(hid, f"{app[1]} host {counters[prefix]:02d}", "Server", crit, False, False, count > 1,
                      platform, app[8], "Infrastructure Operations", f"Production host for {app_id}.")
            host_edges.append((app_id, hid))
    for db_id in data.DR_REPLICAS:
        src = core[db_id]
        add_asset(f"{db_id}-DR", f"{src[1]} (DR replica)", "Database", src[3], False, False, True, src[7],
                  src[8], src[9], f"Disaster recovery replica of {db_id}.", env="Disaster Recovery")
    for app_id in data.STAGING_APPS:
        src = core[app_id]
        add_asset(f"{app_id}-STG", f"{src[1]} (staging)", src[2], "Medium", False, False, False, src[7],
                  src[8], src[9], f"Pre-production environment for {app_id}.", env="Staging")
    for i in range(1, data.NETWORK_SWITCHES + 1):
        add_asset(f"NET-SW-{i:03d}", f"Data Centre Core Switch {i:02d}", "Network Device", "High", False, False, True,
                  "Spine/leaf switching fabric", "Infrastructure", "Network Engineering", "Data centre switching fabric.")
    db.flush()

    edges = list(data.ASSET_DEPENDENCIES) + EXTRA_DEPENDENCIES + host_edges
    edges += [(db_id, f"NET-SW-{(i % data.NETWORK_SWITCHES) + 1:03d}") for i, db_id in enumerate(data.DR_REPLICAS)]
    for a, b in edges:
        kind = "hosted on" if "-SRV-" in b else "runtime"
        db.add(AssetDependency(asset_id=a, depends_on_asset_id=b, dependency_type=kind))
    for sid, assets in data.SERVICE_DEPENDENCIES.items():
        for aid in assets:
            db.add(ServiceAssetDependency(service_id=sid, asset_id=aid, role="core"))
    db.flush()


def build_controls(db: Session, users: dict[str, User]) -> None:
    for spec in data.CONTROLS:
        rule = get_rule(spec["rule_key"])
        params = dict(spec["parameters"])
        db.add(
            Control(
                id=spec["id"],
                name=spec["name"],
                description=spec["description"],
                domain=spec["domain"],
                objective=spec["objective"],
                risk_addressed=spec["risk_addressed"],
                owner_id=users[spec["owner"]].id,
                frequency=spec["frequency"],
                rule_key=spec["rule_key"],
                rule_parameters=params,
                evaluation_rule=rule.summary,
                evidence_category=rule.evidence_category,
                required_evidence=spec["required_evidence"],
                failure_severity=spec["failure_severity"],
                current_status="Not Assessed",
            )
        )
        db.flush()
        for aid in spec["scopes"]:
            db.add(ControlAssetScope(control_id=spec["id"], asset_id=aid))
    db.flush()


def build_risks(db: Session, users: dict[str, User], anchor: datetime) -> None:
    for spec in data.RISKS:
        db.add(
            Risk(
                id=spec["id"],
                title=spec["title"],
                description=spec["description"],
                category=spec["category"],
                owner_id=users[spec["owner"]].id,
                inherent_rating=spec["inherent"],
                residual_rating=spec["residual"],
                treatment=spec["treatment"],
                treatment_plan=spec["plan"],
                review_date=anchor + timedelta(days=spec["review_days"]),
                status=spec.get("status", "Open"),
                created_at=anchor - timedelta(days=180),
                updated_at=anchor - timedelta(days=20),
            )
        )
        db.flush()
        for cid in spec["controls"]:
            db.add(RiskControlMapping(risk_id=spec["id"], control_id=cid))
        for sid in spec["services"]:
            db.add(RiskServiceMapping(risk_id=spec["id"], service_id=sid))
    db.flush()


# --------------------------------------------------------------------------- workflow events
def _workflow_events(users: dict[str, User], clock: Clock) -> list[dict]:
    u = users
    return [
        {"day": -78, "key": ("CTRL-VM-001", "PAY-API-001"), "status": "In Progress", "actor": u["marcus.chen@alphabetabank.example"],
         "note": "Patched build of TLS library scheduled in emergency change window.",
         "action": ("Upgrade TLS termination library on payment API", "marcus.chen@alphabetabank.example", -70, "Completed")},
        {"day": -60, "key": ("CTRL-IAM-001", "IDP-AD-001"), "status": "In Progress", "actor": u["daniel.okafor@alphabetabank.example"],
         "note": "Owner of legacy enterprise admin account identified; FIDO2 enrolment scheduled."},
        {"day": -57, "key": ("CTRL-BCP-001", "DB-TXN-001"), "status": "In Progress", "actor": u["james.whitfield@alphabetabank.example"],
         "note": "Recovery test RT-TXN-0231 achieved partial recovery only. Full re-test requires DR storage expansion.",
         "action": ("Execute full restore test of Payment Transaction Database to DR site", "james.whitfield@alphabetabank.example", -27, "In Progress")},
        {"day": -57, "key": ("CTRL-DP-001", "DWH-001"), "accept": {
            "actor": u["priya.raman@alphabetabank.example"], "approver": u["catherine.hale@alphabetabank.example"], "expires_day": 33,
            "justification": "Legacy archive volume holds historic regulatory extracts only; access is restricted to two "
                             "break-glass DBA accounts with session recording. Migration to the encrypted storage tier is "
                             "funded and scheduled within the acceptance window."}},
        {"day": -42, "key": ("CTRL-TPR-001", "EXT-KYC-001"), "status": "In Progress", "actor": u["elena.rossi@alphabetabank.example"],
         "note": "Reassessment questionnaire issued to VeriPass; awaiting independent assurance report.",
         "action": ("Obtain current independent assurance report and complete reassessment", "elena.rossi@alphabetabank.example", 12, "In Progress")},
        {"day": -39, "key": ("CTRL-IAM-002", "TRD-APP-001"), "actor": u["daniel.okafor@alphabetabank.example"],
         "note": "Recertification campaign scheduled; awaiting sign-off from markets desk heads."},
        {"day": -24, "key": ("CTRL-VM-001", "WEB-BANK-001"), "status": "In Progress", "actor": u["marcus.chen@alphabetabank.example"],
         "note": "WAF virtual patch applied at edge as interim mitigation; framework upgrade requires regression testing.",
         "action": ("Upgrade web framework to patched release on production web tier", "marcus.chen@alphabetabank.example", -10, "In Progress")},
        {"day": -15, "key": ("CTRL-CHG-001", "CARD-APP-001"), "status": "In Progress", "actor": u["aisha.patel@alphabetabank.example"],
         "note": "Deployments traced to a legacy deploy job that bypasses the approval gate; retrospective review raised."},
        {"day": -6, "key": ("CTRL-END-001", "TRD-SRV-003"), "status": "In Progress", "actor": u["sofia.alvarez@alphabetabank.example"],
         "note": "Host isolated pending EDR reinstall; no malicious activity observed in network telemetry.",
         "action": ("Reinstall and re-register EDR agent on TRD-SRV-003", "sofia.alvarez@alphabetabank.example", 2, "Planned")},
    ]


def _apply_event(db: Session, ev: dict, users: dict[str, User], clock: Clock) -> None:
    control_id, asset_id = ev["key"]
    finding = db.scalar(
        select(Finding).where(Finding.control_id == control_id, Finding.asset_id == asset_id, Finding.status != "Resolved")
    )
    if finding is None:
        raise RuntimeError(f"Seed workflow event references missing finding {control_id}/{asset_id}")
    at = clock.at(ev["day"]) + timedelta(hours=3)
    if "accept" in ev:
        acc = ev["accept"]
        frm = finding.status
        finding.status = "Risk Accepted"
        finding.acceptance_justification = acc["justification"]
        finding.acceptance_approver_id = acc["approver"].id
        finding.acceptance_expires_at = clock.at(acc["expires_day"])
        finding.accepted_by_id = acc["actor"].id
        finding.accepted_at = at
        db.add(RemediationActivity(
            finding_id=finding.id, actor_id=acc["actor"].id, activity_type="risk_acceptance", from_status=frm,
            to_status="Risk Accepted", created_at=at,
            message=f"Risk accepted until {clock.at(acc['expires_day']).date().isoformat()} with accountable approver "
                    f"{acc['approver'].full_name}. Justification: {acc['justification']}"))
        return
    actor = ev["actor"]
    if ev.get("status"):
        frm = finding.status
        finding.status = ev["status"]
        db.add(RemediationActivity(finding_id=finding.id, actor_id=actor.id, activity_type="status_change",
                                   from_status=frm, to_status=ev["status"], created_at=at,
                                   message=f"Status changed from {frm} to {ev['status']}. Note: {ev['note']}"))
    else:
        db.add(RemediationActivity(finding_id=finding.id, actor_id=actor.id, activity_type="note",
                                   created_at=at, message=ev["note"]))
    if ev.get("action"):
        title, owner_email, due_day, status = ev["action"]
        action = RemediationAction(finding_id=finding.id, title=title, owner_id=users[owner_email].id,
                                   status=status, due_date=clock.at(due_day), created_at=at, created_by_id=actor.id,
                                   completed_at=clock.at(due_day + 3) if status == "Completed" else None)
        db.add(action)
        db.flush()
        db.add(RemediationActivity(finding_id=finding.id, actor_id=actor.id, activity_type="action_created",
                                   action_id=action.id, created_at=at,
                                   message=f"Remediation action {action.ref} created: {title}."))
    finding.updated_at = at


# --------------------------------------------------------------------------- history
def _evidence_streams(db: Session) -> list[tuple[str, str]]:
    rows = db.execute(select(ControlAssetScope.asset_id, Control.evidence_category).join(Control)).all()
    return sorted({(a, c) for a, c in rows})


def replay_history(db: Session, users: dict[str, User], clock: Clock, log=log_default) -> None:
    streams = _evidence_streams(db)
    gctx = load_graph(db)
    events = sorted(_workflow_events(users, clock), key=lambda e: e["day"])
    applied = 0
    for day in RUN_DAYS:
        run_time = clock.at(day)
        collected = run_time - timedelta(hours=2)
        for asset_id, category in streams:
            payload = GENERATORS[category](asset_id, day, clock)
            if payload is None:
                continue
            content = json.dumps(payload, indent=2).encode()
            ingest_evidence(
                db,
                content=content,
                filename=f"{category}_{asset_id}_{collected:%Y%m%d}.json",
                category=category,
                source=SOURCES[category],
                asset_id=asset_id,
                collected_at=collected,
                uploaded_at=collected + timedelta(minutes=10),
                now=run_time,
            )
        db.commit()
        run = run_assessment(db, triggered_by=None, trigger="scheduled", as_of=run_time, graph_ctx=gctx)
        while applied < len(events) and events[applied]["day"] <= day:
            _apply_event(db, events[applied], users, clock)
            applied += 1
        db.commit()
        r = run.summary["results"]
        log(f"  run {run.ref} day {day:+d}: {r['Effective']} effective, {r['Ineffective']} ineffective, "
            f"{r['Needs Review']} needs review, +{len(run.summary['findings_created'])} findings, "
            f"{len(run.summary['findings_resolved'])} resolved")


def seed_environment(db: Session, *, anchor: datetime | None = None, log=log_default, actor: User | None = None) -> dict:
    anchor = (anchor or utcnow()).replace(minute=0, second=0, microsecond=0)
    clock = Clock(anchor)
    log("Purging existing domain data...")
    purge_domain_data(db)
    log("Creating roles and users...")
    users = ensure_roles_and_users(db)
    settings_service.ensure_defaults(db)
    log("Building asset inventory, services and dependencies...")
    build_inventory(db, anchor - timedelta(days=400))
    log("Defining controls and scopes...")
    build_controls(db, users)
    log("Creating risk register...")
    build_risks(db, users, anchor)
    db.commit()
    log(f"Replaying {len(RUN_DAYS)} assessment cycles over 90 days of evidence...")
    replay_history(db, users, clock, log)
    record_audit(db, "demo.seeded", actor=actor, entity_type="environment", entity_id="alphabetabank",
                 details={"anchor": anchor.isoformat(), "runs": len(RUN_DAYS)})
    db.commit()
    return {"anchor": anchor.isoformat(), "runs": len(RUN_DAYS)}
