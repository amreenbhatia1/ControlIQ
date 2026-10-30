import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import ControlAssessment
from app.services.assessment_service import replay_assessment
from app.services.evidence_service import storage_root
from tests import factory as f


def _assessment(db, world):
    f.ingest(db, "privileged_accounts", "IDP-CORE-001", f.mfa_payload(missing=("admin_002",)))
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
    return db.scalar(select(ControlAssessment))


def test_orm_refuses_to_update_assessments(db, world):
    a = _assessment(db, world)
    a.result = "Effective"
    with pytest.raises(Exception, match="immutable"):
        db.flush()
    db.rollback()


def test_database_trigger_blocks_update_and_delete(db, world):
    a = _assessment(db, world)
    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(text("UPDATE control_assessments SET result = 'Effective' WHERE id = :id"), {"id": a.id})
    db.rollback()
    with pytest.raises(DBAPIError, match="cannot be deleted"):
        db.execute(text("DELETE FROM control_assessments WHERE id = :id"), {"id": a.id})
    db.rollback()
    assert db.get(ControlAssessment, a.id).result == "Ineffective"


def test_replay_reproduces_recorded_result(db, world):
    a = _assessment(db, world)
    r = replay_assessment(a)
    assert r["reproducible"] is True
    assert r["replayed_result"] == "Ineffective"
    assert all(v for v in r["checks"].values())


def test_replay_detects_tampered_evidence_file(db, world):
    a = _assessment(db, world)
    path = storage_root() / a.evidence[0].file_ref
    path.write_bytes(path.read_bytes() + b" ")
    r = replay_assessment(a)
    assert r["checks"]["evidence_integrity_verified"] is False
    assert r["reproducible"] is False
