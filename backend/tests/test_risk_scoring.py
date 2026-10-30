import pytest

from app.risk.scoring import (
    DEFAULT_WEIGHTS,
    ScoringConfigError,
    ScoringInputs,
    calculate_risk_score,
    severity_for_score,
    validate_weights,
)


def _inputs(**overrides) -> ScoringInputs:
    base = dict(
        control_id="CTRL-IAM-001",
        control_name="Privileged MFA Enforcement",
        control_severity="Critical",
        failure_magnitude=1.0,
        asset_id="IDP-CORE-001",
        asset_criticality="Critical",
        internet_exposed=True,
        privileged_access_hub=False,
        exploit_applicable=False,
        exploit_signal=False,
        highest_service_tier="Tier 1",
        highest_service_name="Payment Processing",
        impacted_service_count=1,
        compensating_controls=[],
    )
    base.update(overrides)
    return ScoringInputs(**base)


def test_maximum_inputs_score_100_and_contributions_sum_to_score():
    result = calculate_risk_score(_inputs())
    assert result["score"] == 100
    assert result["severity"] == "Critical"
    assert sum(f["contribution"] for f in result["factors"]) == pytest.approx(100)
    assert [f["key"] for f in result["factors"]] == list(DEFAULT_WEIGHTS)
    assert "not a statistically validated" in result["disclaimer"]


def test_mixed_inputs_produce_documented_score():
    # severity 0.75*(0.8+0)=0.6 -> 15.0 ; asset Medium 0.5 -> 10.0 ; internal 0.4 -> 8.0 ;
    # no service 0.2 -> 4.0 ; effective compensating credit 0.15 -> 0.85 -> 12.75 ; total 49.75 -> 50
    result = calculate_risk_score(_inputs(
        control_severity="High", failure_magnitude=0.0, asset_criticality="Medium", internet_exposed=False,
        highest_service_tier=None, highest_service_name=None, impacted_service_count=0,
        compensating_controls=[{"control_id": "CTRL-LOG-001", "credit": 0.15, "status": "Effective"}],
    ))
    contributions = {f["key"]: f["contribution"] for f in result["factors"]}
    assert contributions == {
        "control_failure_severity": 15.0,
        "asset_criticality": 10.0,
        "exposure": 8.0,
        "business_service_criticality": 4.0,
        "compensating_control_weakness": 12.75,
    }
    assert result["score"] == 50
    assert result["severity"] == "Medium"


def test_compensating_control_only_counts_when_effective():
    failing = calculate_risk_score(_inputs(
        compensating_controls=[{"control_id": "CTRL-LOG-001", "credit": 0.15, "status": "Ineffective"}]))
    effective = calculate_risk_score(_inputs(
        compensating_controls=[{"control_id": "CTRL-LOG-001", "credit": 0.15, "status": "Effective"}]))
    comp = lambda r: next(f for f in r["factors"] if f["key"] == "compensating_control_weakness")  # noqa: E731
    assert comp(failing)["value"] == 1.0
    assert comp(effective)["value"] == 0.85
    assert "not currently verified" in comp(failing)["rationale"]


def test_exploit_signal_uplifts_exposure_for_vulnerability_controls():
    internal = dict(internet_exposed=False, exploit_applicable=True)
    without = calculate_risk_score(_inputs(**internal, exploit_signal=False))
    with_kev = calculate_risk_score(_inputs(**internal, exploit_signal=True))
    exp = lambda r: next(f for f in r["factors"] if f["key"] == "exposure")["value"]  # noqa: E731
    assert exp(without) == 0.4
    assert exp(with_kev) == pytest.approx(0.6)


def test_privileged_hub_exposure_and_service_breadth_uplift():
    r = calculate_risk_score(_inputs(internet_exposed=False, privileged_access_hub=True,
                                     highest_service_tier="Tier 2", impacted_service_count=3))
    factors = {f["key"]: f for f in r["factors"]}
    assert factors["exposure"]["value"] == 0.8
    assert factors["business_service_criticality"]["value"] == pytest.approx(0.65 + 0.1)


def test_custom_weights_change_score_and_are_validated():
    weights = {**DEFAULT_WEIGHTS, "exposure": 0.10, "asset_criticality": 0.30}
    r = calculate_risk_score(_inputs(internet_exposed=False), weights)
    assert r["weights"]["asset_criticality"] == 0.30
    assert next(f for f in r["factors"] if f["key"] == "exposure")["contribution"] == 4.0

    with pytest.raises(ScoringConfigError):
        validate_weights({**DEFAULT_WEIGHTS, "exposure": 0.5})
    with pytest.raises(ScoringConfigError):
        validate_weights({"exposure": 1.0})


def test_severity_bands():
    assert severity_for_score(80) == "Critical"
    assert severity_for_score(79) == "High"
    assert severity_for_score(60) == "High"
    assert severity_for_score(40) == "Medium"
    assert severity_for_score(39) == "Low"
    assert severity_for_score(70, {"Critical": 70, "High": 50, "Medium": 30}) == "Critical"
