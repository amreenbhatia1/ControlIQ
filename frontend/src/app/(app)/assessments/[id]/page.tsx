"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, Lock, RotateCcw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  Field,
  FindingStatusBadge,
  JsonView,
  KeyValues,
  LoadingBlock,
  PageHeader,
  RefLink,
  SectionCard,
  Spinner,
  StatusBadge,
  ValidationBadge,
} from "@/components/common";
import { api } from "@/lib/api";
import { formatDateTime, shortHash } from "@/lib/format";
import type { Assessment, Evidence } from "@/lib/types";

type Neighbour = { id: number; ref: string; result: string; assessed_at: string } | null;

type AssessmentDetail = {
  assessment: Assessment;
  rule_parameters: Record<string, unknown>;
  details: Record<string, unknown>;
  control: { id: string; name: string; domain: string; evaluation_rule: string; required_evidence: string };
  evidence: Evidence[];
  finding: { id: number; ref: string; title: string; status: string } | null;
  previous: Neighbour;
  next: Neighbour;
  run: { id: number; ref: string } | null;
};

type Replay = {
  reproducible: boolean;
  checks: Record<string, boolean | null>;
  replayed_result: string;
  replayed_explanation: string;
  recorded_input_hash: string;
  recomputed_input_hash: string;
  current_rule_version: string;
};

const CHECK_LABELS: Record<string, string> = {
  rule_version_matches: "Rule version matches current implementation",
  result_matches: "Re-executed result matches recorded result",
  explanation_matches: "Re-executed explanation matches",
  input_hash_matches: "Input hash recomputes identically",
  evidence_integrity_verified: "Stored evidence file matches its SHA-256",
};

function NeighbourLink({ n, dir }: { n: Neighbour; dir: "prev" | "next" }) {
  if (!n) return <span className="text-xs text-muted-foreground">{dir === "prev" ? "First assessment" : "Latest assessment"}</span>;
  return (
    <Link href={`/assessments/${n.id}`} className="inline-flex items-center gap-1.5 text-xs hover:underline">
      {dir === "prev" && <ChevronLeft className="size-3.5" />}
      <span className="mono text-blue-700">{n.ref}</span>
      <StatusBadge status={n.result} />
      {dir === "next" && <ChevronRight className="size-3.5" />}
    </Link>
  );
}

export default function AssessmentPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["assessment", id],
    queryFn: () => api<AssessmentDetail>(`/assessments/${id}`),
  });
  const replay = useMutation({ mutationFn: () => api<Replay>(`/assessments/${id}/replay`, { method: "POST" }) });

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !data) return <LoadingBlock rows={10} />;
  const a = data.assessment;

  return (
    <div>
      <Link href={`/controls/${a.control_id}`} className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-3.5" /> {a.control_id}
      </Link>
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-1">
            <Lock className="size-3" /> Immutable assessment record
          </span>
        }
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span className="mono">{a.ref}</span> <StatusBadge status={a.result} />
          </span>
        }
        description={`${a.control_id} ${a.control_name} on ${a.asset_id ?? "—"} ${a.asset_name ? `(${a.asset_name})` : ""}`}
        actions={
          <Button size="sm" variant="outline" onClick={() => replay.mutate()} disabled={replay.isPending}>
            {replay.isPending ? <Spinner className="size-3.5" /> : <RotateCcw className="size-3.5" />} Replay &amp; verify
          </Button>
        }
      />

      <div className="mb-4 flex items-center justify-between rounded-lg border bg-card px-4 py-2">
        <NeighbourLink n={data.previous} dir="prev" />
        <span className="text-xs text-muted-foreground">History for this control and asset</span>
        <NeighbourLink n={data.next} dir="next" />
      </div>

      {replay.data && (
        <SectionCard
          className={replay.data.reproducible ? "mb-4 border-emerald-300" : "mb-4 border-red-300"}
          title={
            <span className="flex items-center gap-1.5">
              {replay.data.reproducible ? (
                <CheckCircle2 className="size-4 text-emerald-600" />
              ) : (
                <XCircle className="size-4 text-red-600" />
              )}
              {replay.data.reproducible ? "Assessment reproduced exactly" : "Assessment could not be reproduced"}
            </span>
          }
          description="The recorded rule was re-executed against the recorded evidence, parameters and asset context"
        >
          <ul className="space-y-1.5 text-sm">
            {Object.entries(replay.data.checks).map(([k, v]) => (
              <li key={k} className="flex items-center gap-2">
                {v === null ? (
                  <span className="size-4 text-center text-muted-foreground">–</span>
                ) : v ? (
                  <CheckCircle2 className="size-4 text-emerald-600" />
                ) : (
                  <XCircle className="size-4 text-red-600" />
                )}
                {CHECK_LABELS[k] ?? k}
                {v === null && <span className="text-xs text-muted-foreground">(no evidence recorded)</span>}
              </li>
            ))}
          </ul>
          <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
            <Field label="Recorded input hash">
              <span className="mono text-xs font-normal">{replay.data.recorded_input_hash}</span>
            </Field>
            <Field label="Recomputed input hash">
              <span className="mono text-xs font-normal">{replay.data.recomputed_input_hash}</span>
            </Field>
          </div>
        </SectionCard>
      )}
      {replay.error && <ErrorState error={replay.error} />}

      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard title="Outcome" className="xl:col-span-2">
          <p className="text-sm">{a.explanation}</p>
          <dl className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-3">
            <Field label="Assessed at (as-of)">{formatDateTime(a.assessed_at)}</Field>
            <Field label="Recorded at">{formatDateTime(a.recorded_at)}</Field>
            <Field label="Run">{data.run ? <RefLink href={`/controls?run=${data.run.id}`}>{data.run.ref}</RefLink> : "—"}</Field>
            <Field label="Rule">
              <span className="mono text-xs">
                {a.rule_key} v{a.rule_version}
              </span>
            </Field>
            <Field label="Input hash (SHA-256)">
              <span className="mono text-xs" title={a.input_hash}>
                {shortHash(a.input_hash, 20)}
              </span>
            </Field>
            <Field label="Finding">
              {data.finding ? (
                <span className="flex items-center gap-2">
                  <RefLink href={`/findings/${data.finding.id}`}>{data.finding.ref}</RefLink>
                  <FindingStatusBadge status={data.finding.status} />
                </span>
              ) : (
                "None"
              )}
            </Field>
          </dl>
        </SectionCard>
        <SectionCard title="Rule parameters at evaluation time">
          <JsonView value={data.rule_parameters} className="max-h-64" />
          <p className="mt-2 text-xs text-muted-foreground">{data.control.evaluation_rule}</p>
        </SectionCard>
      </div>

      <SectionCard title="Evaluation details" description="Intermediate values the rule recorded, including the asset context it used" className="mt-4">
        <KeyValues data={data.details} />
      </SectionCard>

      <SectionCard title="Evidence used" description={data.control.required_evidence} className="mt-4">
        {data.evidence.length === 0 ? (
          <EmptyState title="No evidence was available" description="The control could not be evaluated, so the result is Needs Review." />
        ) : (
          <div className="space-y-4">
            {data.evidence.map((e) => (
              <div key={e.id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <RefLink href={`/evidence/${e.id}`}>{e.ref}</RefLink>
                    <ValidationBadge status={e.validation_status} />
                    <span className="text-xs text-muted-foreground">{e.original_filename}</span>
                  </div>
                  <span className="mono text-[11px] text-muted-foreground" title={e.sha256}>
                    sha256 {shortHash(e.sha256, 16)}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {e.source} · collected {formatDateTime(e.collected_at)} · uploaded {formatDateTime(e.uploaded_at)}
                  {e.uploaded_by ? ` by ${e.uploaded_by}` : ""}
                </div>
                {e.payload !== undefined && e.payload !== null && <JsonView value={e.payload} className="mt-2" />}
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
