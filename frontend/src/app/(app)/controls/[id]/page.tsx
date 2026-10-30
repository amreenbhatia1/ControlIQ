"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, Play } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  Field,
  FindingStatusBadge,
  JsonView,
  LoadingBlock,
  PageHeader,
  RefLink,
  ScorePill,
  SectionCard,
  SeverityBadge,
  Spinner,
  StatusBadge,
} from "@/components/common";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { STATUS_COLORS, formatDate, formatDateTime, relativeTime } from "@/lib/format";
import { useCan, useRunAssessment } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { Assessment, ControlItem, Evidence, Finding } from "@/lib/types";

type ControlDetail = {
  control: ControlItem;
  rule: {
    key: string;
    version: string;
    title: string;
    summary: string;
    effective_parameters: Record<string, unknown>;
    evidence_category: string;
    evidence_category_label: string;
    remediation_guidance: string;
  };
  scopes: {
    asset_id: string;
    asset_name: string;
    asset_type: string;
    criticality: string;
    status: string;
    last_assessed_at: string | null;
    latest_assessment: Assessment | null;
    latest_evidence: Evidence | null;
  }[];
  history: { evaluated_at: string; effective: number; ineffective: number; needs_review: number }[];
  findings: Finding[];
};

export default function ControlDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const can = useCan();
  const run = useRunAssessment();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["control", id],
    queryFn: () => api<ControlDetail>(`/controls/${id}`),
  });
  const history = useQuery({
    queryKey: ["control", id, "assessments"],
    queryFn: () => api<Assessment[]>(`/controls/${id}/history`, { params: { limit: 40 } }),
  });

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !data) return <LoadingBlock rows={10} />;
  const { control: c, rule } = data;
  const chart = data.history.map((h) => ({ ...h, label: formatDate(h.evaluated_at).slice(0, 6) }));

  return (
    <div>
      <Link href="/controls" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-3.5" /> Control Monitoring
      </Link>
      <PageHeader
        eyebrow={`${c.id} · ${c.domain}`}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {c.name} <StatusBadge status={c.current_status} />
          </span>
        }
        description={c.description}
        actions={
          can(PERM.ASSESSMENTS_RUN) && (
            <Button size="sm" onClick={() => run.mutate([c.id])} disabled={run.isPending}>
              {run.isPending ? <Spinner className="size-3.5" /> : <Play className="size-3.5" />} Assess this control
            </Button>
          )
        }
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard title="Control definition" className="xl:col-span-2">
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Objective">{c.objective}</Field>
            <Field label="Risk addressed">{c.risk_addressed}</Field>
            <Field label="Control owner">{c.owner ? `${c.owner.full_name} — ${c.owner.title}` : "Unassigned"}</Field>
            <Field label="Assessment frequency">{c.frequency}</Field>
            <Field label="Required evidence">{c.required_evidence}</Field>
            <Field label="Failure severity">
              <SeverityBadge severity={c.failure_severity} />
            </Field>
            <Field label="Last assessed">{formatDateTime(c.last_assessed_at)}</Field>
            <Field label="Next scheduled assessment">{formatDateTime(c.next_assessment_at)}</Field>
          </dl>
        </SectionCard>
        <SectionCard title="Evaluation rule" description={`${rule.key} · version ${rule.version}`}>
          <div className="space-y-3 text-sm">
            <p>{rule.summary}</p>
            <div>
              <div className="mb-1 text-xs text-muted-foreground">Effective parameters</div>
              <JsonView value={rule.effective_parameters} className="max-h-48" />
            </div>
            <Field label="Evidence category">{rule.evidence_category_label}</Field>
            <Field label="Remediation guidance">
              <span className="font-normal">{rule.remediation_guidance}</span>
            </Field>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="Asset scopes" description="Latest immutable assessment and evidence per in-scope asset" className="mt-4" bodyClassName="p-0">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-xs">Asset</TableHead>
              <TableHead className="text-xs">Status</TableHead>
              <TableHead className="text-xs">Latest assessment</TableHead>
              <TableHead className="text-xs">Evidence</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.scopes.map((s) => (
              <TableRow key={s.asset_id}>
                <TableCell className="align-top">
                  <RefLink href={`/assets/${s.asset_id}`}>{s.asset_id}</RefLink>
                  <div className="text-sm font-medium">{s.asset_name}</div>
                  <div className="text-xs text-muted-foreground">
                    {s.asset_type} · {s.criticality}
                  </div>
                </TableCell>
                <TableCell className="align-top">
                  <StatusBadge status={s.status} />
                </TableCell>
                <TableCell className="max-w-md align-top whitespace-normal">
                  {s.latest_assessment ? (
                    <>
                      <RefLink href={`/assessments/${s.latest_assessment.id}`}>{s.latest_assessment.ref}</RefLink>
                      <span className="ml-2 text-xs text-muted-foreground">{relativeTime(s.latest_assessment.assessed_at)}</span>
                      <p className="mt-0.5 text-xs">{s.latest_assessment.explanation}</p>
                      {s.latest_assessment.finding_ref && (
                        <div className="mt-1 text-xs">
                          Finding <RefLink href={`/findings/${s.latest_assessment.finding_id}`}>{s.latest_assessment.finding_ref}</RefLink>
                        </div>
                      )}
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">Not yet assessed</span>
                  )}
                </TableCell>
                <TableCell className="align-top">
                  {s.latest_evidence ? (
                    <>
                      <RefLink href={`/evidence/${s.latest_evidence.id}`}>{s.latest_evidence.ref}</RefLink>
                      <div className="text-xs text-muted-foreground">collected {relativeTime(s.latest_evidence.collected_at)}</div>
                      <div className="max-w-56 truncate text-xs text-muted-foreground">{s.latest_evidence.source}</div>
                    </>
                  ) : (
                    <span className="text-xs text-amber-700">No evidence on file</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </SectionCard>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <SectionCard title="Assessment outcomes over time" description="Asset scopes by result for each run in the last 90 days">
          {chart.length === 0 ? (
            <EmptyState title="No assessment history" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={chart} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={16} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                  <ChartTooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                    labelFormatter={(_, p) => (p?.[0] ? formatDateTime(p[0].payload.evaluated_at) : "")}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="effective" name="Effective" stackId="a" fill={STATUS_COLORS.Effective} maxBarSize={14} />
                  <Bar dataKey="needs_review" name="Needs Review" stackId="a" fill={STATUS_COLORS["Needs Review"]} maxBarSize={14} />
                  <Bar dataKey="ineffective" name="Ineffective" stackId="a" fill={STATUS_COLORS.Ineffective} maxBarSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
        <SectionCard title="Findings raised by this control" bodyClassName="p-0">
          {data.findings.length === 0 ? (
            <EmptyState title="No findings recorded" />
          ) : (
            <ul className="max-h-72 divide-y overflow-auto">
              {data.findings.map((f) => (
                <li
                  key={f.id}
                  className="flex cursor-pointer items-center gap-3 px-4 py-2 hover:bg-muted/40"
                  onClick={() => router.push(`/findings/${f.id}`)}
                >
                  <ScorePill score={f.risk_score} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{f.title}</div>
                    <div className="text-xs text-muted-foreground">
                      <span className="mono">{f.ref}</span> · detected {formatDate(f.detected_at)}
                    </div>
                  </div>
                  <FindingStatusBadge status={f.status} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Recent assessments" description="Immutable records — each links to its evidence, parameters and input hash" className="mt-4" bodyClassName="p-0">
        {history.isLoading ? (
          <LoadingBlock className="p-4" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-xs">Assessment</TableHead>
                <TableHead className="text-xs">Asset</TableHead>
                <TableHead className="text-xs">Result</TableHead>
                <TableHead className="text-xs">Explanation</TableHead>
                <TableHead className="text-xs">Assessed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(history.data ?? []).map((a) => (
                <TableRow key={a.id} className="cursor-pointer" onClick={() => router.push(`/assessments/${a.id}`)}>
                  <TableCell>
                    <span className="mono text-xs font-medium text-blue-700">{a.ref}</span>
                    <div className="mono text-[11px] text-muted-foreground">{a.run_ref}</div>
                  </TableCell>
                  <TableCell className="mono text-xs">{a.asset_id}</TableCell>
                  <TableCell>
                    <StatusBadge status={a.result} />
                  </TableCell>
                  <TableCell className="max-w-lg text-xs whitespace-normal">{a.explanation}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">{formatDateTime(a.assessed_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>
    </div>
  );
}
