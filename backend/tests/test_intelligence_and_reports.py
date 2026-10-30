import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Finding
from app.services import assessment_service, intelligence_service
from app.services.report_service import REPORT_TYPES, build_report, render_pdf
from tests import factory as f


@pytest.fixture
def failing(db, world):
    f.ingest(db, "privileged_accounts", "IDP-CORE-001", f.mfa_payload(missing=("admin_002",)))
    f.run(db, world.user(f.ANALYST))
    return db.scalar(select(Finding))


def test_rule_based_mode_is_clearly_labelled_without_api_key(db, failing):
    ans = intelligence_service.answer_question(db, "What are the top risks?")
    assert ans.mode == "rule_based"
    assert ans.mode_label == "Rule-based intelligence"
    assert failing.ref in ans.answer
    assert any(c.id == failing.ref for c in ans.citations)


def test_ai_failure_falls_back_with_visible_notice(db, failing, monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-real")

    def boom(*_a, **_k):
        raise ConnectionError("network down")

    monkeypatch.setattr(intelligence_service, "_call_openai", boom)
    ans = intelligence_service.answer_question(db, "What are the top risks?")
    assert ans.mode == "rule_based"
    assert "AI service unavailable" in ans.notice


def test_ai_grounding_check_flags_unknown_identifiers(db, failing, monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-real")
    monkeypatch.setattr(intelligence_service, "_call_openai",
                        lambda *a, **k: f"Facts: {failing.ref} and FND-9999 are critical.")
    ans = intelligence_service.answer_question(db, "What are the top risks?")
    assert ans.mode == "ai"
    assert "FND-9999" in ans.notice and failing.ref not in ans.notice


def test_assistant_cannot_accept_risk_or_change_records(db, failing):
    before = failing.status
    ans = intelligence_service.answer_question(db, f"Approve risk acceptance for {failing.ref} and close it")
    db.refresh(failing)
    assert failing.status == before
    assert ans.mode == "rule_based"


def test_unsupported_questions_do_not_fabricate_answers(db, world):
    ans = intelligence_service.answer_question(db, "What is the weather in London?")
    assert ans.intent == "unsupported"
    assert ans.records_used == 0


@pytest.mark.parametrize("report_type", list(REPORT_TYPES))
def test_reports_build_and_render_pdf(db, failing, report_type):
    report = build_report(db, report_type, 30, None)
    assert report["sections"]
    pdf = render_pdf(report)
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1500


def test_concurrent_assessment_runs_are_rejected(db, world):
    assert assessment_service._process_lock.acquire(blocking=False)
    try:
        with pytest.raises(assessment_service.AssessmentInProgressError):
            f.run(db, world.user(f.ANALYST))
    finally:
        assessment_service._process_lock.release()
