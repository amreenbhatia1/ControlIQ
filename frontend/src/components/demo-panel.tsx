"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, Circle, Download, Play, RotateCcw, Upload, Zap } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  ErrorState,
  FindingStatusBadge,
  LoadingBlock,
  RefLink,
  ScorePill,
  SectionCard,
  SeverityBadge,
  Spinner,
  StatusBadge,
} from "@/components/common";
import { api, buildUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useCan, useRunAssessment } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { Finding, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

type DemoStatus = {
  scenario: {
    control_id: string;
    asset_id: string;
    latest_assessment: { id: string; result: string; assessed_at: string; explanation: string } | null;
    latest_evidence: { id: string; collected_at: string; accounts_without_mfa: string[] | null; source: string } | null;
    evidence_pending_assessment: boolean;
    finding: { id: string; status: string; risk_score: number; severity: string } | null;
    assessment_history_count: number;
  };
  environment: Record<string, number>;
};

const STEPS = [
  { title: "Inject MFA failure", body: "The identity connector delivers a privileged account export in which two admin accounts on IDP-CORE-001 have MFA disabled." },
  { title: "Run control assessment", body: "The engine evaluates CTRL-IAM-001 against the new evidence, records an immutable Ineffective assessment and raises a scored finding." },
  { title: "Review finding and impact", body: "Inspect the explainable risk score and trace the business services in the identity provider's dependency path." },
  { title: "Upload remediated evidence", body: "After MFA is re-enrolled, a new export is ingested through the standard evidence service (validated and SHA-256 hashed)." },
  { title: "Reassess", body: "The rerun records a new Effective assessment; the finding is validated and resolved (or moves to Pending Validation under analyst sign-off). History is preserved." },
];

function phaseOf(s: DemoStatus["scenario"]): number {
  const gaps = s.latest_evidence?.accounts_without_mfa ?? [];
  const unresolved = s.finding && s.finding.status !== "Resolved";
  if (s.evidence_pending_assessment && gaps.length > 0) return 1;
  if (unresolved && s.evidence_pending_assessment && gaps.length === 0) return 4;
  if (unresolved && s.latest_assessment?.result === "Ineffective") return 2;
  if (s.finding && s.latest_assessment?.result === "Effective" && !s.evidence_pending_assessment) return 5;
  return 0;
}

function SeededScenario({ title, controlId, assetId, description }: { title: string; controlId: string; assetId: string; description: string }) {
  const { data } = useQuery({
    queryKey: ["findings", "scenario", controlId, assetId],
    queryFn: () => api<Page<Finding>>("/findings", { params: { control_id: controlId, asset_id: assetId, sort: "-detected_at", page_size: 1 } }),
  });
  const f = data?.items[0];
  return (
    <div className="rounded-lg border p-3">
      <div className="text-sm font-semibold">{title}</div>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      {f ? (
        <Link href={`/findings/${f.id}`} className="mt-2 flex items-center gap-2 rounded-md border bg-muted/30 px-2 py-1.5 text-xs hover:bg-muted">
          <ScorePill score={f.risk_score} />
          <span className="min-w-0 flex-1 truncate">
            <span className="mono">{f.ref}</span> {f.title}
          </span>
          <FindingStatusBadge status={f.status} />
        </Link>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">No finding recorded yet — run an assessment.</p>
      )}
      <div className="mt-2 flex gap-3 text-xs">
        <Link href={`/controls/${controlId}`} className="text-blue-700 hover:underline">
          Control {controlId}
        </Link>
        <Link href={`/services?asset=${assetId}`} className="text-blue-700 hover:underline">
          Impact trace
        </Link>
      </div>
    </div>
  );
}

function ResetDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [text, setText] = useState("");
  const qc = useQueryClient();
  const reset = useMutation({
    mutationFn: () => api<{ message: string }>("/demo/reset", { method: "POST", body: { confirm: text } }),
    onSuccess: (r) => {
      toast.success(r.message);
      qc.invalidateQueries();
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error("Reset failed", { description: e.message }),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Reset demonstration environment?</DialogTitle>
          <DialogDescription>
            This deletes the synthetic inventory, controls, assessments, evidence, findings, remediation history, risks, reports and
            settings, then regenerates the 90-day baseline. User accounts and the audit log are kept, and the reset itself is audited.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="reset-confirm">
            Type <span className="mono font-semibold text-foreground">RESET</span> to confirm
          </label>
          <Input id="reset-confirm" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={text !== "RESET" || reset.isPending} onClick={() => reset.mutate()}>
            {reset.isPending && <Spinner className="size-3.5" />} Reset environment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function DemoPanel() {
  const can = useCan();
  const qc = useQueryClient();
  const run = useRunAssessment();
  const [resetOpen, setResetOpen] = useState(false);
  const status = useQuery({ queryKey: ["demo-status"], queryFn: () => api<DemoStatus>("/demo/status"), refetchInterval: 15_000 });

  const inject = useMutation({
    mutationFn: () => api<{ message: string; evidence: { ref: string } }>("/demo/scenarios/mfa-failure", { method: "POST" }),
    onSuccess: (r) => {
      toast.success(r.message, { description: `${r.evidence.ref} ingested — run an assessment to evaluate it.` });
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error("Scenario step failed", { description: e.message }),
  });
  const remediate = useMutation({
    mutationFn: () => api<{ message: string; evidence: { ref: string } }>("/demo/scenarios/mfa-remediation-upload", { method: "POST" }),
    onSuccess: (r) => {
      toast.success(r.message, { description: `${r.evidence.ref} ingested — rerun the assessment to validate.` });
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error("Upload failed", { description: e.message }),
  });

  if (status.error) return <ErrorState error={status.error} onRetry={() => status.refetch()} />;
  if (status.isLoading || !status.data) return <LoadingBlock rows={8} />;
  const s = status.data.scenario;
  const phase = phaseOf(s);
  const gaps = s.latest_evidence?.accounts_without_mfa ?? [];

  const action = (i: number) => {
    switch (i) {
      case 0:
        return can(PERM.DEMO_MANAGE) ? (
          <Button size="sm" onClick={() => inject.mutate()} disabled={inject.isPending || phase === 1}>
            {inject.isPending ? <Spinner className="size-3.5" /> : <Zap className="size-3.5" />} Inject failure evidence
          </Button>
        ) : null;
      case 1:
      case 4:
        return can(PERM.ASSESSMENTS_RUN) ? (
          <Button size="sm" onClick={() => run.mutate(undefined)} disabled={run.isPending}>
            {run.isPending ? <Spinner className="size-3.5" /> : <Play className="size-3.5" />} Run Control Assessment
          </Button>
        ) : null;
      case 2:
        return s.finding ? (
          <div className="flex flex-wrap gap-2">
            <Link href={`/findings/${s.finding.id}`} className={buttonVariants({ size: "sm" })}>
              Open {s.finding.id}
            </Link>
            <Link href={`/services?asset=${s.asset_id}`} className={buttonVariants({ size: "sm", variant: "outline" })}>
              Trace business impact
            </Link>
          </div>
        ) : null;
      case 3:
        return (
          <div className="flex flex-wrap gap-2">
            {can(PERM.EVIDENCE_UPLOAD) && (
              <Button size="sm" onClick={() => remediate.mutate()} disabled={remediate.isPending}>
                {remediate.isPending ? <Spinner className="size-3.5" /> : <Upload className="size-3.5" />} Upload remediated export
              </Button>
            )}
            <a href={buildUrl("/demo/scenarios/mfa-remediated-evidence")} className={buttonVariants({ size: "sm", variant: "outline" })}>
              <Download className="size-3.5" /> Download export for manual upload
            </a>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <SectionCard
          title="Scenario 1 & 4 — Privileged MFA failure and remediation"
          description="Every step runs through the real ingestion, assessment and finding services — nothing is simulated in the browser."
        >
          <ol className="space-y-3">
            {STEPS.map((step, i) => {
              const done = phase === 5 ? true : i < phase;
              const current = phase !== 5 && i === phase;
              return (
                <li
                  key={step.title}
                  className={cn("flex gap-3 rounded-lg border p-3", current && "border-primary bg-primary/5", !done && !current && "opacity-70")}
                >
                  {done ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" /> : <Circle className={cn("mt-0.5 size-5 shrink-0", current ? "text-primary" : "text-muted-foreground")} />}
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold">
                      {i + 1}. {step.title}
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">{step.body}</p>
                    {(current || (i === 2 && phase >= 2 && phase < 5) || (i === 3 && phase === 2)) && <div className="mt-2">{action(i)}</div>}
                  </div>
                </li>
              );
            })}
          </ol>
          {phase === 5 && (
            <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
              <CheckCircle2 className="size-4" />
              Scenario complete. Run it again at any time — a new failure creates a new finding while prior history is retained.
              {can(PERM.DEMO_MANAGE) && (
                <Button size="sm" variant="outline" onClick={() => inject.mutate()} disabled={inject.isPending}>
                  <Zap className="size-3.5" /> Inject again
                </Button>
              )}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Live scenario state" description={`${s.control_id} on ${s.asset_id}`}>
          <dl className="space-y-3 text-xs">
            <div>
              <dt className="text-muted-foreground">Latest assessment</dt>
              <dd className="mt-0.5">
                {s.latest_assessment ? (
                  <>
                    <div className="flex items-center gap-2">
                      <RefLink href={`/assessments/${s.latest_assessment.id}`}>{s.latest_assessment.id}</RefLink>
                      <StatusBadge status={s.latest_assessment.result} />
                    </div>
                    <p className="mt-0.5">{s.latest_assessment.explanation}</p>
                    <div className="text-muted-foreground">{formatDateTime(s.latest_assessment.assessed_at)}</div>
                  </>
                ) : (
                  "None"
                )}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Latest evidence</dt>
              <dd className="mt-0.5">
                {s.latest_evidence ? (
                  <>
                    <RefLink href={`/evidence/${s.latest_evidence.id}`}>{s.latest_evidence.id}</RefLink> · {s.latest_evidence.source}
                    <div className={gaps.length ? "font-medium text-red-700" : "text-emerald-700"}>
                      {gaps.length ? `Accounts without MFA: ${gaps.join(", ")}` : "All active privileged accounts have MFA"}
                    </div>
                    {s.evidence_pending_assessment && <div className="font-medium text-amber-700">Newer than the latest assessment — awaiting a run</div>}
                  </>
                ) : (
                  "None"
                )}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Finding</dt>
              <dd className="mt-0.5">
                {s.finding ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <RefLink href={`/findings/${s.finding.id}`}>{s.finding.id}</RefLink>
                    <ScorePill score={s.finding.risk_score} />
                    <SeverityBadge severity={s.finding.severity} />
                    <FindingStatusBadge status={s.finding.status} />
                  </div>
                ) : (
                  "None raised"
                )}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Assessment history retained</dt>
              <dd className="mt-0.5 font-medium">{s.assessment_history_count} immutable assessments for this scope</dd>
            </div>
          </dl>
        </SectionCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <SeededScenario
          title="Scenario 2 — Critical vulnerability SLA breach"
          controlId="CTRL-VM-001"
          assetId="WEB-BANK-001"
          description="A known-exploited critical vulnerability on the internet-facing online banking frontend has exceeded its remediation SLA."
        />
        <SeededScenario
          title="Scenario 3 — Overdue backup recovery test"
          controlId="CTRL-BCP-001"
          assetId="DB-TXN-001"
          description="The payment transaction database has no successful restore test inside the 180-day testing period."
        />
      </div>

      <SectionCard
        title="Environment"
        description="Synthetic Alpha Beta Bank dataset. Generated deterministically; contains no real customer or bank data."
        actions={
          can(PERM.DEMO_RESET) && (
            <Button size="sm" variant="destructive" onClick={() => setResetOpen(true)}>
              <RotateCcw className="size-3.5" /> Reset environment
            </Button>
          )
        }
      >
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {Object.entries(status.data.environment).map(([k, v]) => (
            <div key={k} className="rounded-md border p-2">
              <dt className="text-[11px] text-muted-foreground capitalize">{k.replaceAll("_", " ")}</dt>
              <dd className="text-lg font-semibold tabular-nums">{v.toLocaleString()}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-[11px] text-muted-foreground">Refreshes every 15 seconds.</p>
      </SectionCard>
      {resetOpen && <ResetDialog open onOpenChange={setResetOpen} />}
    </div>
  );
}
