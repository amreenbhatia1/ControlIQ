"""Explainable, deterministic risk prioritisation model.

The score (0-100) is a weighted sum of five normalised factors. It is a prioritisation aid for
remediation sequencing. It is NOT a statistically validated prediction of loss or likelihood.
"""

from dataclasses import dataclass, field

METHODOLOGY_VERSION = "1.0"

DEFAULT_WEIGHTS: dict[str, float] = {
    "control_failure_severity": 0.25,
    "asset_criticality": 0.20,
    "exposure": 0.20,
    "business_service_criticality": 0.20,
    "compensating_control_weakness": 0.15,
}

DEFAULT_BANDS = {"Critical": 80, "High": 60, "Medium": 40}

FACTOR_LABELS = {
    "control_failure_severity": "Control failure severity",
    "asset_criticality": "Asset criticality",
    "exposure": "Exposure & exploit intelligence",
    "business_service_criticality": "Business service criticality",
    "compensating_control_weakness": "Compensating control weakness",
}

SEVERITY_SCALE = {"Critical": 1.0, "High": 0.75, "Medium": 0.5, "Low": 0.25}
TIER_SCALE = {"Tier 1": 1.0, "Tier 2": 0.65, "Tier 3": 0.35}
NO_SERVICE_VALUE = 0.2
INTERNET_EXPOSURE = 1.0
PRIVILEGED_PLANE_EXPOSURE = 0.8
INTERNAL_EXPOSURE = 0.4
EXPLOIT_UPLIFT = 0.2
SERVICE_BREADTH_UPLIFT = 0.05

DISCLAIMER = (
    "Risk scores are a deterministic prioritisation aid derived from configured weights. They are not a "
    "statistically validated prediction of financial loss or incident likelihood."
)


@dataclass
class ScoringInputs:
    control_id: str
    control_name: str
    control_severity: str
    failure_magnitude: float
    asset_id: str
    asset_criticality: str
    internet_exposed: bool
    privileged_access_hub: bool
    exploit_applicable: bool
    exploit_signal: bool
    highest_service_tier: str | None
    highest_service_name: str | None
    impacted_service_count: int
    compensating_controls: list[dict] = field(default_factory=list)


class ScoringConfigError(ValueError):
    pass


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    if set(weights) != set(DEFAULT_WEIGHTS):
        raise ScoringConfigError(f"Weights must define exactly: {', '.join(DEFAULT_WEIGHTS)}")
    if any(not isinstance(v, (int, float)) or v < 0 or v > 1 for v in weights.values()):
        raise ScoringConfigError("Each weight must be between 0 and 1")
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise ScoringConfigError(f"Weights must sum to 1.0 (currently {total:.3f})")
    return {k: float(v) for k, v in weights.items()}


def severity_for_score(score: int, bands: dict[str, int] | None = None) -> str:
    b = bands or DEFAULT_BANDS
    if score >= b["Critical"]:
        return "Critical"
    if score >= b["High"]:
        return "High"
    if score >= b["Medium"]:
        return "Medium"
    return "Low"


def _factor(key: str, value: float, weight: float, rationale: str, inputs: dict) -> dict:
    value = round(max(0.0, min(1.0, value)), 4)
    return {
        "key": key,
        "label": FACTOR_LABELS[key],
        "weight": weight,
        "value": value,
        "contribution": round(value * weight * 100, 2),
        "max_contribution": round(weight * 100, 2),
        "rationale": rationale,
        "inputs": inputs,
    }


def calculate_risk_score(
    inp: ScoringInputs, weights: dict[str, float] | None = None, bands: dict[str, int] | None = None
) -> dict:
    w = validate_weights(weights or DEFAULT_WEIGHTS)
    magnitude = max(0.0, min(1.0, inp.failure_magnitude))

    base = SEVERITY_SCALE[inp.control_severity]
    sev_value = base * (0.8 + 0.2 * magnitude)
    f_sev = _factor(
        "control_failure_severity",
        sev_value,
        w["control_failure_severity"],
        f"{inp.control_name} is classified {inp.control_severity} on failure (base {base:.2f}); "
        f"breadth of failure {magnitude:.0%} scales the value between 80% and 100% of base.",
        {"control_severity": inp.control_severity, "failure_magnitude": round(magnitude, 3)},
    )

    crit = SEVERITY_SCALE[inp.asset_criticality]
    f_asset = _factor(
        "asset_criticality",
        crit,
        w["asset_criticality"],
        f"{inp.asset_id} is rated {inp.asset_criticality} criticality in the asset inventory.",
        {"asset_criticality": inp.asset_criticality},
    )

    if inp.internet_exposed:
        exp, exp_reason = INTERNET_EXPOSURE, "Asset is directly reachable from the internet"
    elif inp.privileged_access_hub:
        exp, exp_reason = PRIVILEGED_PLANE_EXPOSURE, "Asset brokers privileged/administrative access across systems"
    else:
        exp, exp_reason = INTERNAL_EXPOSURE, "Asset is internal-only with no privileged access brokering"
    if inp.exploit_applicable and inp.exploit_signal:
        exp = min(1.0, exp + EXPLOIT_UPLIFT)
        exp_reason += "; exploit intelligence marks at least one failing item as known-exploited (+0.20)"
    elif inp.exploit_applicable:
        exp_reason += "; no known-exploited indicator on failing items"
    f_exp = _factor(
        "exposure",
        exp,
        w["exposure"],
        exp_reason + ".",
        {
            "internet_exposed": inp.internet_exposed,
            "privileged_access_hub": inp.privileged_access_hub,
            "exploit_applicable": inp.exploit_applicable,
            "known_exploited": inp.exploit_signal,
        },
    )

    if inp.highest_service_tier:
        svc = TIER_SCALE[inp.highest_service_tier] + SERVICE_BREADTH_UPLIFT * max(0, inp.impacted_service_count - 1)
        svc_reason = (
            f"Highest dependent service is {inp.highest_service_name} ({inp.highest_service_tier}); "
            f"{inp.impacted_service_count} business service(s) depend on this asset directly or transitively "
            f"(+{SERVICE_BREADTH_UPLIFT:.2f} per additional service)."
        )
    else:
        svc = NO_SERVICE_VALUE
        svc_reason = "No mapped business service depends on this asset."
    f_svc = _factor(
        "business_service_criticality",
        svc,
        w["business_service_criticality"],
        svc_reason,
        {
            "highest_service_tier": inp.highest_service_tier,
            "highest_service": inp.highest_service_name,
            "impacted_service_count": inp.impacted_service_count,
        },
    )

    effective = [c for c in inp.compensating_controls if c.get("status") == "Effective"]
    credit = min(1.0, sum(float(c.get("credit", 0)) for c in effective))
    if effective:
        comp_reason = "Verified compensating control(s): " + ", ".join(
            f"{c['control_id']} (credit {float(c['credit']):.2f})" for c in effective
        )
    elif inp.compensating_controls:
        comp_reason = "Designated compensating control(s) are not currently verified as effective: " + ", ".join(
            f"{c['control_id']} ({c.get('status', 'Not Assessed')})" for c in inp.compensating_controls
        )
    else:
        comp_reason = "No compensating control is defined for this control failure."
    f_comp = _factor(
        "compensating_control_weakness",
        1.0 - credit,
        w["compensating_control_weakness"],
        comp_reason + ".",
        {"compensating_controls": inp.compensating_controls, "total_credit": round(credit, 3)},
    )

    factors = [f_sev, f_asset, f_exp, f_svc, f_comp]
    score = int(round(sum(f["contribution"] for f in factors)))
    score = max(0, min(100, score))
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "score": score,
        "severity": severity_for_score(score, bands),
        "weights": w,
        "bands": bands or DEFAULT_BANDS,
        "factors": factors,
        "disclaimer": DISCLAIMER,
    }
