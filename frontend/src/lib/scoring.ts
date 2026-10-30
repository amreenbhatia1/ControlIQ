import type { ScoreBreakdown, Severity } from "./types";

/**
 * Client-side mirror of the backend scoring formula, used only for the interactive
 * "what-if" view. Stored finding scores always come from the backend.
 */
export function severityForScore(score: number, bands: Record<string, number>): Severity {
  if (score >= bands.Critical) return "Critical";
  if (score >= bands.High) return "High";
  if (score >= bands.Medium) return "Medium";
  return "Low";
}

export function normaliseWeights(weights: Record<string, number>): Record<string, number> {
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  if (total <= 0) return weights;
  return Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, v / total]));
}

export function recomputeScore(
  breakdown: ScoreBreakdown,
  overrides: { values?: Record<string, number>; weights?: Record<string, number> } = {},
): { score: number; severity: Severity; contributions: Record<string, number> } {
  const weights = overrides.weights ?? breakdown.weights;
  const contributions: Record<string, number> = {};
  let total = 0;
  for (const f of breakdown.factors) {
    const override = overrides.values?.[f.key];
    const weight = weights[f.key] ?? 0;
    const value = Math.max(0, Math.min(1, override ?? f.value));
    const unchanged = override === undefined && weight === f.weight;
    const c = unchanged ? f.contribution : Math.round(value * weight * 100 * 100) / 100;
    contributions[f.key] = c;
    total += c;
  }
  const score = Math.max(0, Math.min(100, roundHalfEven(total)));
  return { score, severity: severityForScore(score, breakdown.bands), contributions };
}

/** Matches Python's round(): exact halves round to the nearest even integer. */
export function roundHalfEven(x: number): number {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

export function weightsSumToOne(weights: Record<string, number>): boolean {
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  return Math.abs(total - 1) <= 0.001;
}
