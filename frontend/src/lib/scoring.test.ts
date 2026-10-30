import { describe, expect, it } from "vitest";
import { normaliseWeights, recomputeScore, roundHalfEven, severityForScore, weightsSumToOne } from "./scoring";
import type { ScoreBreakdown } from "./types";

const BANDS = { Critical: 80, High: 60, Medium: 40 };
const WEIGHTS = {
  control_failure_severity: 0.25,
  asset_criticality: 0.2,
  exposure: 0.2,
  business_service_criticality: 0.2,
  compensating_control_weakness: 0.15,
};

// Values and contributions as recorded by the backend for the Scenario 1 MFA finding.
function mfaBreakdown(): ScoreBreakdown {
  const factor = (key: string, value: number, contribution: number) => ({
    key,
    label: key,
    weight: WEIGHTS[key as keyof typeof WEIGHTS],
    value,
    contribution,
    max_contribution: WEIGHTS[key as keyof typeof WEIGHTS] * 100,
    rationale: "",
    inputs: {},
  });
  return {
    methodology_version: "1.0",
    score: 90,
    severity: "Critical",
    weights: WEIGHTS,
    bands: BANDS,
    factors: [
      factor("control_failure_severity", 0.8667, 21.67),
      factor("asset_criticality", 1, 20),
      factor("exposure", 0.8, 16),
      factor("business_service_criticality", 1, 20),
      factor("compensating_control_weakness", 0.85, 12.75),
    ],
    disclaimer: "",
  };
}

describe("severityForScore", () => {
  it("applies band thresholds inclusively", () => {
    expect(severityForScore(80, BANDS)).toBe("Critical");
    expect(severityForScore(79, BANDS)).toBe("High");
    expect(severityForScore(60, BANDS)).toBe("High");
    expect(severityForScore(40, BANDS)).toBe("Medium");
    expect(severityForScore(39, BANDS)).toBe("Low");
  });
});

describe("roundHalfEven", () => {
  it("matches Python's round() on exact halves", () => {
    expect(roundHalfEven(90.5)).toBe(90);
    expect(roundHalfEven(91.5)).toBe(92);
    expect(roundHalfEven(0.5)).toBe(0);
    expect(roundHalfEven(90.51)).toBe(91);
    expect(roundHalfEven(90.49)).toBe(90);
  });
});

describe("recomputeScore", () => {
  it("reproduces the recorded backend score when nothing is changed", () => {
    const b = mfaBreakdown();
    const r = recomputeScore(b);
    expect(r.score).toBe(b.score);
    expect(r.severity).toBe("Critical");
    expect(r.contributions.compensating_control_weakness).toBe(12.75);
  });

  it("recomputes only the factors that are overridden", () => {
    const r = recomputeScore(mfaBreakdown(), { values: { exposure: 0 } });
    expect(r.contributions.exposure).toBe(0);
    expect(r.contributions.asset_criticality).toBe(20);
    expect(r.score).toBe(74);
    expect(r.severity).toBe("High");
  });

  it("clamps factor values to the 0–1 range", () => {
    const r = recomputeScore(mfaBreakdown(), { values: { exposure: 5 } });
    expect(r.contributions.exposure).toBe(20);
  });

  it("applies alternative weights to every factor", () => {
    const weights = { ...WEIGHTS, exposure: 0, asset_criticality: 0.4 };
    const r = recomputeScore(mfaBreakdown(), { weights });
    expect(r.contributions.exposure).toBe(0);
    expect(r.contributions.asset_criticality).toBe(40);
  });
});

describe("weights", () => {
  it("validates that weights sum to one within tolerance", () => {
    expect(weightsSumToOne(WEIGHTS)).toBe(true);
    expect(weightsSumToOne({ ...WEIGHTS, exposure: 0.3 })).toBe(false);
    expect(weightsSumToOne({ ...WEIGHTS, exposure: 0.2005 })).toBe(true);
  });

  it("normalises weights proportionally", () => {
    const n = normaliseWeights({ a: 1, b: 3 });
    expect(n.a).toBeCloseTo(0.25);
    expect(n.b).toBeCloseTo(0.75);
    expect(normaliseWeights({ a: 0, b: 0 })).toEqual({ a: 0, b: 0 });
  });
});
