"""Pure evaluation pipeline shared by live assessments, seeding, and replay verification."""

import hashlib
import json
from datetime import datetime

from app.controls.base import INEFFECTIVE, NEEDS_REVIEW, EvidenceInput, RuleOutcome
from app.controls.evidence_schemas import EvidenceSchemaError, parse_payload
from app.controls.rules import ControlRule
from app.core.time import iso

ALLOWED_POLICY_RESULTS = (NEEDS_REVIEW, INEFFECTIVE)


def canonical_json(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_input_hash(
    rule: ControlRule, params: dict, context: dict, evidence: EvidenceInput | None, as_of: datetime
) -> str:
    material = {
        "rule": rule.key,
        "rule_version": rule.version,
        "parameters": params,
        "context": context,
        "as_of": iso(as_of),
        "evidence": None
        if evidence is None
        else {"id": evidence.evidence_id, "sha256": evidence.sha256, "collected_at": iso(evidence.collected_at)},
    }
    return hashlib.sha256(canonical_json(material).encode()).hexdigest()


def _policy_result(params: dict, key: str) -> str:
    value = params.get(key, NEEDS_REVIEW)
    return value if value in ALLOWED_POLICY_RESULTS else NEEDS_REVIEW


def evaluate_scope(
    rule: ControlRule,
    params: dict,
    context: dict,
    evidence: EvidenceInput | None,
    as_of: datetime,
) -> RuleOutcome:
    """Evaluate a single control scope.

    Evidence policy (applied before the rule):
    - Missing evidence -> `missing_evidence_result` (default Needs Review).
    - Evidence older than `evidence_max_age_days` -> `stale_evidence_result` (default Needs Review).
    - Evidence that failed schema validation -> Needs Review.
    - Evidence for a different asset -> Needs Review.
    Missing or stale evidence never implies failure unless the control explicitly configures it.
    """
    asset_id = context.get("asset_id")
    if evidence is None:
        return RuleOutcome(
            _policy_result(params, "missing_evidence_result"),
            f"No {rule.evidence_category.replace('_', ' ')} evidence is on record for {asset_id} "
            f"as of {iso(as_of)}. Effectiveness cannot be concluded without evidence.",
            {"evidence_issue": "missing"},
        )

    max_age = params.get("evidence_max_age_days")
    age_days = (as_of - evidence.collected_at).total_seconds() / 86400
    if max_age is not None and age_days > float(max_age):
        return RuleOutcome(
            _policy_result(params, "stale_evidence_result"),
            f"Most recent evidence was collected {int(age_days)} days ago, exceeding the "
            f"{max_age}-day freshness requirement. A current evidence submission is required.",
            {"evidence_issue": "stale", "evidence_age_days": round(age_days, 1), "max_age_days": max_age},
        )

    if evidence.validation_status != "Valid":
        return RuleOutcome(
            NEEDS_REVIEW,
            "The latest evidence did not pass schema validation and cannot be evaluated automatically.",
            {"evidence_issue": "invalid"},
        )

    try:
        typed = parse_payload(rule.evidence_category, evidence.payload)
    except EvidenceSchemaError as exc:
        return RuleOutcome(
            NEEDS_REVIEW,
            f"Evidence could not be interpreted: {exc}",
            {"evidence_issue": "schema_error"},
        )

    if asset_id and getattr(typed, "asset_id", None) != asset_id:
        return RuleOutcome(
            NEEDS_REVIEW,
            f"Evidence references asset '{getattr(typed, 'asset_id', None)}' but the control scope is '{asset_id}'.",
            {"evidence_issue": "asset_mismatch"},
        )

    outcome = rule.evaluate(typed, params, context, as_of)
    outcome.details = {**outcome.details, "evidence_age_days": round(age_days, 1)}
    return outcome
