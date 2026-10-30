"""Role-based access control is enforced by the API, independent of the frontend."""

import json

import pytest

from tests import factory as f

API = "/api/v1"
NEW_ASSET = {
    "id": "TEST-APP-001", "name": "Test Application", "asset_type": "Application", "business_owner": "Payments",
    "technical_owner": "Platform Engineering", "criticality": "High", "service_ids": ["SVC-PAY"],
}


def _mfa_file(payload=None):
    return {"file": ("accounts.json", json.dumps(payload or f.mfa_payload()).encode(), "application/json")}


def test_unauthenticated_requests_are_rejected(client, world):
    for path in ("/dashboard/summary", "/findings", "/assets", "/controls", "/evidence"):
        assert client.get(API + path).status_code == 401
    assert client.post(API + "/assessments/run", json={}).status_code == 401


def test_invalid_login_is_rejected_and_audited(client, world, db):
    r = client.post(API + "/auth/login", json={"email": f.ANALYST, "password": "wrong-password"})
    assert r.status_code == 401
    from sqlalchemy import select

    from app.models import AuditLog

    entry = db.scalar(select(AuditLog).where(AuditLog.action == "auth.login", AuditLog.outcome == "failure"))
    assert entry is not None


def test_session_cookie_is_httponly(client, world):
    r = client.post(API + "/auth/login", json={"email": f.ANALYST, "password": "ControlIQ-Demo-2026!"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_executive_viewer_is_read_only(login, world):
    c = login(f.EXECUTIVE)
    assert c.get(API + "/dashboard/summary").status_code == 200
    assert c.get(API + "/findings").status_code == 200
    assert c.post(API + "/assessments/run", json={}).status_code == 403
    assert c.post(API + "/assets", json=NEW_ASSET).status_code == 403
    assert c.patch(API + "/assets/PAY-API-001", json={"criticality": "Low"}).status_code == 403
    r = c.post(API + "/evidence/upload", files=_mfa_file(),
               data={"category": "privileged_accounts", "asset_id": "IDP-CORE-001"})
    assert r.status_code == 403
    assert c.post(API + "/demo/scenarios/mfa-failure").status_code == 403
    assert c.put(API + "/settings/validation-workflow", json={"mode": "analyst_signoff"}).status_code == 403
    assert c.get(API + "/audit-logs").status_code == 403


def test_control_owner_permissions(login, world, db):
    f.ingest(db, "privileged_accounts", "IDP-CORE-001", f.mfa_payload(missing=("admin_002",)))
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])

    vm_owner = login(f.VM_OWNER)
    assert vm_owner.post(API + "/assets", json=NEW_ASSET).status_code == 403
    # Control owners can run assessments and upload evidence...
    r = vm_owner.post(API + "/evidence/upload", files=_mfa_file(),
                      data={"category": "privileged_accounts", "asset_id": "IDP-CORE-001"})
    assert r.status_code == 201, r.text
    # ...but cannot change findings for controls they neither own nor are assigned.
    r = vm_owner.post(API + "/findings/FND-0001/status", json={"status": "In Progress"})
    assert r.status_code == 403
    assert vm_owner.post(API + "/findings/FND-0001/accept-risk", json={
        "justification": "x" * 60, "approver_id": world.user(f.EXECUTIVE).id,
        "expires_at": "2099-01-01T00:00:00Z"}).status_code in (403, 422)

    iam_owner = login(f.IAM_OWNER)
    r = iam_owner.post(API + "/findings/FND-0001/status", json={"status": "In Progress", "note": "Working on it"})
    assert r.status_code == 200, r.text


def test_permission_denials_are_audited(login, world, db):
    from sqlalchemy import select

    from app.models import AuditLog

    f.ingest(db, "privileged_accounts", "IDP-CORE-001", f.mfa_payload(missing=("admin_002",)))
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])

    c = login(f.EXECUTIVE)
    assert c.post(API + "/assessments/run", json={}).status_code == 403
    role_denial = db.scalar(select(AuditLog).where(AuditLog.action == "authz.denied"))
    assert role_denial.actor_email == f.EXECUTIVE and role_denial.outcome == "denied"
    assert "assessments:run" in role_denial.details["reason"]

    c = login(f.VM_OWNER)
    assert c.post(API + "/findings/FND-0001/status", json={"status": "In Progress"}).status_code == 403
    owner_denial = db.scalar(
        select(AuditLog).where(AuditLog.action == "authz.denied", AuditLog.actor_email == f.VM_OWNER)
    )
    assert owner_denial.details["endpoint"] == "POST /api/v1/findings/FND-0001/status"


def test_risk_analyst_cannot_change_platform_settings_or_reset(login, world):
    c = login(f.ANALYST)
    weights = {"weights": {"control_failure_severity": 0.2, "asset_criticality": 0.2, "exposure": 0.2,
                           "business_service_criticality": 0.2, "compensating_control_weakness": 0.2}}
    assert c.put(API + "/settings/risk-scoring", json=weights).status_code == 403
    assert c.post(API + "/demo/reset", json={"confirm": "RESET"}).status_code == 403
    assert c.get(API + "/audit-logs").status_code == 403
    assert c.post(API + "/assets", json=NEW_ASSET).status_code == 201


def test_administrator_settings_are_validated(login, world):
    c = login(f.ADMIN)
    bad = {"weights": {"control_failure_severity": 0.5, "asset_criticality": 0.5, "exposure": 0.5,
                       "business_service_criticality": 0.2, "compensating_control_weakness": 0.2}}
    assert c.put(API + "/settings/risk-scoring", json=bad).status_code == 422
    good = {"weights": {"control_failure_severity": 0.2, "asset_criticality": 0.2, "exposure": 0.2,
                        "business_service_criticality": 0.2, "compensating_control_weakness": 0.2}}
    assert c.put(API + "/settings/risk-scoring", json=good).status_code == 200
    # Reset requires typed confirmation.
    assert c.post(API + "/demo/reset", json={"confirm": "yes"}).status_code == 422
    assert c.get(API + "/audit-logs").status_code == 200


def test_cross_origin_state_change_is_blocked(login, world):
    c = login(f.ANALYST)
    r = c.post(API + "/assessments/run", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_rate_limit_on_login(client, world):
    from app.core.rate_limit import limiter

    limiter.enabled = True
    codes = [client.post(API + "/auth/login", json={"email": f.ANALYST, "password": "bad"}).status_code
             for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


@pytest.mark.parametrize("path", ["/evidence/1/download", "/findings/FND-9999", "/assets/NOPE"])
def test_unknown_resources_return_404_not_500(login, world, path):
    c = login(f.ANALYST)
    assert c.get(API + path).status_code == 404
