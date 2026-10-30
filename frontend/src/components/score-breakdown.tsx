"use client";

import { useState } from "react";
import { FlaskConical, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { ScorePill, SeverityBadge } from "@/components/common";
import { scoreColor } from "@/lib/format";
import { recomputeScore } from "@/lib/scoring";
import type { ScoreBreakdown } from "@/lib/types";
import { cn } from "@/lib/utils";

function sliderValue(v: number | readonly number[]): number {
  return Array.isArray(v) ? (v[0] as number) : (v as number);
}

export function ScoreBreakdownView({ breakdown }: { breakdown: ScoreBreakdown }) {
  const [whatIf, setWhatIf] = useState(false);
  const [values, setValues] = useState<Record<string, number>>({});
  const sim = recomputeScore(breakdown, { values });
  const changed = Object.keys(values).length > 0;
  const shownScore = whatIf ? sim.score : breakdown.score;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-3">
          <div
            className="flex size-16 items-center justify-center rounded-full border-4 text-xl font-semibold tabular-nums"
            style={{ borderColor: scoreColor(shownScore), color: scoreColor(shownScore) }}
          >
            {shownScore}
          </div>
          <div>
            <div className="text-sm font-medium">{whatIf ? "Simulated score" : "Recorded risk score"}</div>
            <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
              <SeverityBadge severity={whatIf ? sim.severity : breakdown.severity} />
              methodology v{breakdown.methodology_version}
            </div>
          </div>
        </div>
        {whatIf && changed && (
          <div className="text-xs text-muted-foreground">
            Recorded: <ScorePill score={breakdown.score} /> → simulated: <ScorePill score={sim.score} />
          </div>
        )}
        <div className="ml-auto flex gap-2">
          {whatIf && changed && (
            <Button size="sm" variant="ghost" onClick={() => setValues({})}>
              <RotateCcw className="size-3.5" /> Reset
            </Button>
          )}
          <Button size="sm" variant={whatIf ? "secondary" : "outline"} onClick={() => setWhatIf((w) => !w)}>
            <FlaskConical className="size-3.5" /> {whatIf ? "Exit what-if" : "What-if analysis"}
          </Button>
        </div>
      </div>
      {whatIf && (
        <p className="mb-3 rounded-md border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-800">
          Simulation only: adjust factor values to see how the score responds. The stored score is recalculated by the
          backend only when the control is reassessed.
        </p>
      )}
      <ul className="space-y-3">
        {breakdown.factors.map((f) => {
          const value = values[f.key] ?? f.value;
          const contribution = whatIf ? sim.contributions[f.key] : f.contribution;
          const pct = f.max_contribution ? (contribution / f.max_contribution) * 100 : 0;
          return (
            <li key={f.key} className="rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-medium">{f.label}</span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  weight {(f.weight * 100).toFixed(0)}% · value {value.toFixed(2)} ·{" "}
                  <span className="font-semibold text-foreground">
                    +{contribution.toFixed(1)} / {f.max_contribution.toFixed(0)}
                  </span>
                </span>
              </div>
              <div className="mt-1.5 h-2 rounded-full bg-muted">
                <div
                  className={cn("h-2 rounded-full transition-all", whatIf && values[f.key] !== undefined ? "bg-violet-500" : "bg-primary")}
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
              {whatIf && (
                <div className="mt-2.5 px-1">
                  <Slider
                    value={[value]}
                    min={0}
                    max={1}
                    step={0.05}
                    onValueChange={(v) => setValues((prev) => ({ ...prev, [f.key]: sliderValue(v) }))}
                    aria-label={`${f.label} value`}
                  />
                </div>
              )}
              <p className="mt-1.5 text-xs text-muted-foreground">{f.rationale}</p>
              {Object.keys(f.inputs).length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {Object.entries(f.inputs).map(([k, v]) => (
                    <span key={k} className="mono rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {k}={formatInput(v)}
                    </span>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-[11px] text-muted-foreground">{breakdown.disclaimer}</p>
    </div>
  );
}

function formatInput(v: unknown): string {
  if (Array.isArray(v)) return v.length ? v.map(formatInput).join(", ") : "[]";
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    if (typeof o.control_id === "string") return [o.control_id, o.status].filter(Boolean).join(" ");
    return JSON.stringify(v);
  }
  return String(v);
}
