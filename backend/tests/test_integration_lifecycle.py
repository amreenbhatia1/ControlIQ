"""End-to-end lifecycle through the HTTP API:

Evidence -> Assessment -> Finding -> Business impact -> Remediation -> Reassessment -> Resolution,
with assessment history preserved and dashboard metrics updated.
"""

import json

from tests import factory as f

API = "/api/v1"


def _upload(c, payload, filename="accounts.json"):
    r = c.post(API + "/evidence/upload",
               files={"file": (filename, json.dumps(payload).encode(), "application/json")},
               data={"category": "privileged_accounts", "asset_id": "IDP-CORE-001", "control_id": "CTRL-IAM-001",
                     "source": "Identity governance export"})
    assert r.status_code == 201, r.text
    return r.json()


def _run(c):
    r = c.post(API + "/assessments/run", json={"control_ids": ["CTRL-IAM-001", "CTRL-LOG-001"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_evidence_to_resolution_lifecycle(login, world):
    analyst = login(f.ANALYST)

    # 1. Baseline: healthy evidence -> Effective.
    _upload(analyst, f.mfa_payload())
    _run(analyst)
    control = analyst.get(API + "/controls/CTRL-IAM-001").json()
    assert control["control"]["current_status"] == "Effective"
    before = analyst.get(API + "/dashboard/summary").json()["kpis"]
    assert before["unresolved_findings"] == 0

    # 2. Failing evidence -> Ineffective assessment -> finding.
    ev = _upload(analyst, f.mfa_payload(missing=("admin_002", "svc_payops_admin")))
    assert ev["validation_status"] == "Valid"
    run = _run(analyst)
    assert len(run["summary"]["findings_created"]) == 1
    ref = run["summary"]["findings_created"][0]

    detail = analyst.get(f"{API}/findings/{ref}").json()
    finding = detail["finding"]
    assert finding["status"] == "Open"
    assert finding["severity"] in ("Critical", "High")
    assert {s["id"] for s in detail["impacted_services"]} == {"SVC-PAY", "SVC-OLB"}
    assert len(detail["score_breakdown"]["factors"]) == 5

    # Assessment links to the exact evidence used and is reproducible.
    failing_assessment = detail["latest_assessment"]
    a = analyst.get(f"{API}/assessments/{failing_assessment['id']}").json()
    assert a["assessment"]["result"] == "Ineffective"
    assert a["evidence"][0]["ref"] == ev["ref"]
    assert analyst.post(f"{API}/assessments/{failing_assessment['id']}/replay").json()["reproducible"] is True

    # 3. Business impact through the dependency graph.
    g = analyst.get(API + "/business-services/graph", params={"asset_id": "IDP-CORE-001"}).json()
    assert {s["id"] for s in g["focus"]["impacted_services"]} == {"SVC-PAY", "SVC-OLB"}
    assert any(p[0] == "SVC-PAY" for p in g["focus"]["paths"])

    after_fail = analyst.get(API + "/dashboard/summary").json()["kpis"]
    assert after_fail["unresolved_findings"] == 1
    assert after_fail["failed_controls"] == before["failed_controls"] + 1

    # 4. Remediation by the control owner; manual resolution is refused.
    owner = login(f.IAM_OWNER)
    assert owner.post(f"{API}/findings/{ref}/status", json={"status": "Resolved"}).status_code == 422
    assert owner.post(f"{API}/findings/{ref}/status", json={"status": "In Progress", "note": "Enrolling keys"}).status_code == 200
    r = owner.post(f"{API}/findings/{ref}/actions", json={
        "title": "Enforce FIDO2 MFA for flagged accounts", "due_date": "2099-01-01T00:00:00Z",
        "owner_id": world.user(f.IAM_OWNER).id})
    assert r.status_code == 201, r.text
    assert owner.post(f"{API}/findings/{ref}/status", json={
        "status": "Pending Validation", "note": "MFA enforced for both accounts"}).status_code == 200

    # 5. Updated evidence + reassessment validates and resolves the finding.
    _upload(owner, f.mfa_payload(), filename="accounts_remediated.json")
    run2 = _run(owner)
    assert run2["summary"]["findings_resolved"] == [ref]

    final = owner.get(f"{API}/findings/{ref}").json()
    assert final["finding"]["status"] == "Resolved"
    activity = [x["type"] for x in final["activity"]]
    for expected in ("detected", "status_change", "action_created", "validated"):
        assert expected in activity

    # 6. History is preserved: earlier Ineffective assessment still exists, unchanged.
    history = owner.get(API + "/controls/CTRL-IAM-001/history").json()
    results = [h["result"] for h in (history["items"] if isinstance(history, dict) else history)]
    assert results.count("Ineffective") == 1 and results.count("Effective") == 2
    assert owner.get(f"{API}/assessments/{failing_assessment['id']}").json()["assessment"]["result"] == "Ineffective"

    after_fix = owner.get(API + "/dashboard/summary").json()["kpis"]
    assert after_fix["unresolved_findings"] == 0
    assert after_fix["failed_controls"] == before["failed_controls"]
