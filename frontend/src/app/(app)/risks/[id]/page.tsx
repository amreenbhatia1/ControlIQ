"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronLeft, ChevronRight, FileCheck2, Pencil, ShieldCheck, Target, TriangleAlert, Wrench, ClipboardList } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ErrorState,
  Field,
  FindingStatusBadge,
  LoadingBlock,
  PageHeader,
  RefLink,
  ScorePill,
  SectionCard,
  SeverityBadge,
  StatusBadge,
  ValidationBadge,
} from "@/components/common";
import { RiskFormDialog, type RiskSummary } from "@/components/risk-form";
import { api } from "@/lib/api";
import { formatDate, relativeTime, shortHash } from "@/lib/format";
import { useCan } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { Assessment, Evidence, Finding } from "@/lib/types";
import { cn } from "@/lib/utils";

type RiskFinding = Finding & { actions: { ref: string; title: string; status: string; due_date: string }[] };

type RiskDetail = RiskSummary & {
  controls: {
    id: string;
    name: string;
    domain: string;
    status: string;
    scopes: { asset_id: string; status: string; assessment: Assessment | null; evidence: Evidence[] }[];
  }[];
  findings: RiskFinding[];
};

const CHAIN = [
  { icon: Target, label: "Risk" },
  { icon: ShieldCheck, label: "Control" },
  { icon: ClipboardList, label: "Assessment" },
  { icon: FileCheck2, label: "Evidence" },
  { icon: TriangleAlert, label: "Finding" },
  { icon: Wrench, label: "Remediation" },
];

function pickFinding(findings: RiskFinding[], controlId: string, assetId: string): RiskFinding | undefined {
  const matches = findings.filter((f) => f.control_id === controlId && f.asset_id === assetId);
  return matches.find((f) => f.status !== "Resolved") ?? matches[0];
}

function ControlBranch({ control, findings }: { control: RiskDetail["controls"][number]; findings: RiskFinding[] }) {
  const attention = control.scopes.some((s) => s.status !== "Effective");
  const [open, setOpen] = useState(attention);
  const counts = control.scopes.reduce<Record<string, number>>((acc, s) => ({ ...acc, [s.status]: (acc[s.status] ?? 0) + 1 }), {});
  return (
    <li className="rounded-lg border">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/40">
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <ShieldCheck className="size-4 text-blue-700" />
        <div className="min-w-0 flex-1">
          <span className="mono text-xs font-semibold">{control.id}</span> <span className="text-sm font-medium">{control.name}</span>
          <div className="text-[11px] text-muted-foreground">
            {control.scopes.length} asset scopes ·{" "}
            {Object.entries(counts)
              .map(([k, v]) => `${v} ${k}`)
              .join(" · ")}
          </div>
        </div>
        <StatusBadge status={control.status} />
      </button>
      {open && (
        <ul className="space-y-2 border-t bg-muted/20 p-3">
          {control.scopes.map((s) => {
            const f = pickFinding(findings, control.id, s.asset_id);
            return (
              <li key={s.asset_id} className="rounded-md border bg-card p-3">
                <div className="grid gap-3 text-xs lg:grid-cols-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                      <ClipboardList className="size-3" /> Assessment
                    </div>
                    <RefLink href={`/assets/${s.asset_id}`}>{s.asset_id}</RefLink>
                    {s.assessment ? (
                      <>
                        <div className="flex items-center gap-1.5">
                          <RefLink href={`/assessments/${s.assessment.id}`}>{s.assessment.ref}</RefLink>
                          <StatusBadge status={s.assessment.result} />
                        </div>
                        <p className="text-muted-foreground">{s.assessment.explanation}</p>
                        <div className="text-muted-foreground">{relativeTime(s.assessment.assessed_at)}</div>
                      </>
                    ) : (
                      <div className="text-muted-foreground">Not yet assessed</div>
                    )}
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                      <FileCheck2 className="size-3" /> Evidence
                    </div>
                    {s.evidence.length === 0 ? (
                      <div className="text-amber-700">No evidence recorded</div>
                    ) : (
                      s.evidence.map((e) => (
                        <div key={e.id} className="space-y-0.5">
                          <div className="flex items-center gap-1.5">
                            <RefLink href={`/evidence/${e.id}`}>{e.ref}</RefLink>
                            <ValidationBadge status={e.validation_status} />
                          </div>
                          <div className="truncate text-muted-foreground">{e.source}</div>
                          <div className="mono text-[10px] text-muted-foreground">sha256 {shortHash(e.sha256)}</div>
                        </div>
                      ))
                    )}
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                      <TriangleAlert className="size-3" /> Finding
                    </div>
                    {f ? (
                      <>
                        <div className="flex items-center gap-1.5">
                          <RefLink href={`/findings/${f.id}`}>{f.ref}</RefLink>
                          <ScorePill score={f.risk_score} />
                        </div>
                        <FindingStatusBadge status={f.status} />
                        <div className="text-muted-foreground">{f.assigned_owner?.full_name ?? "Unassigned"}</div>
                      </>
                    ) : (
                      <div className="text-muted-foreground">No finding linked</div>
                    )}
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                      <Wrench className="size-3" /> Remediation
                    </div>
                    {f && f.actions.length > 0 ? (
                      f.actions.map((a) => (
                        <div key={a.ref}>
                          <span className="mono">{a.ref}</span> {a.title}
                          <div className="text-muted-foreground">
                            {a.status} · due {formatDate(a.due_date)}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="text-muted-foreground">{f ? "No actions recorded" : "—"}</div>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </li>
  );
}

export default function RiskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const can = useCan();
  const [editing, setEditing] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["risk", id],
    queryFn: () => api<RiskDetail>(`/risks/${id}`),
  });

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !data) return <LoadingBlock rows={10} />;

  const scoped = new Set(data.controls.flatMap((c) => c.scopes.map((s) => `${c.id}:${s.asset_id}`)));
  const otherFindings = data.findings.filter((f) => !scoped.has(`${f.control_id}:${f.asset_id}`));

  return (
    <div>
      <Link href="/risks" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-3.5" /> Risk Register
      </Link>
      <PageHeader
        eyebrow={`${data.id} · ${data.category}`}
        title={data.title}
        description={data.description}
        actions={
          can(PERM.RISKS_WRITE) && (
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              <Pencil className="size-3.5" /> Edit
            </Button>
          )
        }
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard title="Risk profile" className="xl:col-span-2">
          <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Field label="Inherent rating">
              <SeverityBadge severity={data.inherent_rating} />
            </Field>
            <Field label="Residual rating">
              <SeverityBadge severity={data.residual_rating} />
            </Field>
            <Field label="Treatment">{data.treatment}</Field>
            <Field label="Status">{data.status}</Field>
            <Field label="Risk owner">{data.owner?.full_name ?? "Unassigned"}</Field>
            <Field label="Next review">{formatDate(data.review_date)}</Field>
            <Field label="Active findings">
              {data.active_finding_count} of {data.finding_count}
            </Field>
            <Field label="Highest active score">{data.max_active_score ? <ScorePill score={data.max_active_score} /> : "—"}</Field>
          </dl>
          {data.treatment_plan && (
            <div className="mt-4">
              <div className="text-xs text-muted-foreground">Treatment plan</div>
              <p className="mt-0.5 text-sm">{data.treatment_plan}</p>
            </div>
          )}
        </SectionCard>
        <SectionCard title="Business services at risk">
          <div className="flex flex-wrap gap-1.5">
            {data.services.map((s) => (
              <Link key={s.id} href={`/services/${s.id}`} className="rounded-md border px-2 py-1 text-xs hover:bg-muted">
                {s.name} <span className="text-muted-foreground">· {s.tier}</span>
              </Link>
            ))}
            {data.services.length === 0 && <span className="text-xs text-muted-foreground">None mapped</span>}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Traceability"
        description="Each mitigating control's latest assessment per asset, the evidence it used, any resulting finding and its remediation"
        className="mt-4"
      >
        <div className="mb-4 flex flex-wrap items-center gap-1 text-xs">
          {CHAIN.map((c, i) => (
            <span key={c.label} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="size-3.5 text-muted-foreground" />}
              <span className={cn("flex items-center gap-1 rounded-md border px-2 py-1", i === 0 && "border-primary bg-primary text-primary-foreground")}>
                <c.icon className="size-3.5" /> {c.label}
              </span>
            </span>
          ))}
        </div>
        <ul className="space-y-2">
          {data.controls.map((c) => (
            <ControlBranch key={c.id} control={c} findings={data.findings} />
          ))}
        </ul>
        {otherFindings.length > 0 && (
          <div className="mt-4">
            <div className="mb-1 text-xs font-semibold">Other linked findings (asset no longer in control scope)</div>
            <ul className="space-y-1 text-xs">
              {otherFindings.map((f) => (
                <li key={f.id} className="flex items-center gap-2">
                  <RefLink href={`/findings/${f.id}`}>{f.ref}</RefLink> {f.title} <FindingStatusBadge status={f.status} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </SectionCard>
      {editing && <RiskFormDialog open onOpenChange={setEditing} risk={data} />}
    </div>
  );
}
