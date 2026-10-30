"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertOctagon,
  ArrowRight,
  CheckCircle2,
  Clock,
  FileWarning,
  Network,
  Play,
  RefreshCw,
  ShieldX,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  FindingStatusBadge,
  KpiCard,
  LoadingBlock,
  PageHeader,
  ScorePill,
  SectionCard,
  SeverityBadge,
  Spinner,
} from "@/components/common";
import { IntelAnswerView } from "@/components/intel-answer";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, relativeTime, SEVERITY_COLORS, SEVERITY_ORDER, scoreColor } from "@/lib/format";
import { useCan, useRunAssessment } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { DashboardSummary, IntelAnswer, TrendPoint } from "@/lib/types";
import { cn } from "@/lib/utils";

const RANGES = [7, 30, 90] as const;

function TrendChart() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);
  const { data, isLoading, error } = useQuery({
    queryKey: ["trend", days],
    queryFn: () => api<{ days: number; points: TrendPoint[] }>("/dashboard/trend", { params: { days } }),
  });
  const points = (data?.points ?? []).map((p) => ({ ...p, label: formatDate(p.evaluated_at).slice(0, 6) }));
  return (
    <SectionCard
      title="Control effectiveness trend"
      description="Each point is a recorded assessment run. Effectiveness excludes Not Assessed instances."
      actions={
        <div className="flex rounded-md border p-0.5">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setDays(r)}
              className={cn(
                "rounded px-2 py-0.5 text-xs font-medium",
                days === r ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {r}d
            </button>
          ))}
        </div>
      }
    >
      {error ? (
        <ErrorState error={error} />
      ) : isLoading ? (
        <LoadingBlock rows={6} />
      ) : points.length === 0 ? (
        <EmptyState title="No assessment runs in this period" />
      ) : (
        <div className="h-72">
          <ResponsiveContainer>
            <ComposedChart data={points} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={16} />
              <YAxis yAxisId="count" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis
                yAxisId="pct"
                orientation="right"
                domain={[0, 100]}
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v}%`}
              />
              <ChartTooltip
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
                labelFormatter={(_, p) => (p?.[0] ? formatDateTime(p[0].payload.evaluated_at) : "")}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="count" dataKey="ineffective" name="Ineffective" stackId="s" fill="#dc2626" radius={[0, 0, 0, 0]} maxBarSize={18} />
              <Bar yAxisId="count" dataKey="needs_review" name="Needs Review" stackId="s" fill="#f59e0b" radius={[3, 3, 0, 0]} maxBarSize={18} />
              <Line
                yAxisId="pct"
                type="monotone"
                dataKey="effectiveness_rate"
                name="Effectiveness %"
                stroke="#1e3a8a"
                strokeWidth={2.5}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </SectionCard>
  );
}

function SeverityChart({ data }: { data: DashboardSummary["severity_distribution"] }) {
  const total = data.reduce((a, b) => a + b.count, 0);
  return (
    <SectionCard title="Unresolved findings by severity" description="Excludes resolved and risk-accepted findings">
      {total === 0 ? (
        <EmptyState title="No unresolved findings" />
      ) : (
        <div className="flex items-center gap-4">
          <div className="relative h-44 w-44 shrink-0">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={data} dataKey="count" nameKey="severity" innerRadius={52} outerRadius={78} paddingAngle={2} stroke="none">
                  {data.map((d) => (
                    <Cell key={d.severity} fill={SEVERITY_COLORS[d.severity]} />
                  ))}
                </Pie>
                <ChartTooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-semibold">{total}</span>
              <span className="text-[11px] text-muted-foreground">unresolved</span>
            </div>
          </div>
          <ul className="flex-1 space-y-2">
            {SEVERITY_ORDER.map((s) => {
              const c = data.find((d) => d.severity === s)?.count ?? 0;
              return (
                <li key={s}>
                  <Link href={`/findings?severity=${s}&view=unresolved`} className="flex items-center justify-between text-sm hover:underline">
                    <span className="flex items-center gap-2">
                      <span className="size-2.5 rounded-sm" style={{ backgroundColor: SEVERITY_COLORS[s] }} />
                      {s}
                    </span>
                    <span className="font-semibold tabular-nums">{c}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

function DomainChart({ data }: { data: DashboardSummary["domain_distribution"] }) {
  const rows = data.map((d) => ({ ...d, short: d.domain.replace(" and ", " & ").replace("Management", "Mgmt") }));
  return (
    <SectionCard title="Unresolved findings by control domain">
      <div className="h-64">
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 12, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="short" width={150} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <ChartTooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            {SEVERITY_ORDER.map((s, i) => (
              <Bar
                key={s}
                dataKey={s}
                stackId="d"
                fill={SEVERITY_COLORS[s]}
                maxBarSize={16}
                radius={i === SEVERITY_ORDER.length - 1 ? [0, 3, 3, 0] : 0}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </SectionCard>
  );
}

function ServicesAtRisk({ data }: { data: DashboardSummary["services_at_risk"] }) {
  return (
    <SectionCard
      title="Business services at risk"
      description="Potential exposure index = 0.7 × highest open finding score + 0.3 × mean of top three"
      actions={
        <Link href="/services" className="text-xs font-medium text-blue-700 hover:underline">
          Dependency map
        </Link>
      }
      bodyClassName="p-0"
    >
      {data.length === 0 ? (
        <EmptyState title="No services with unresolved findings in their dependency path" />
      ) : (
        <ul className="divide-y">
          {data.map((s) => (
            <li key={s.service_id}>
              <Link href={`/services/${s.service_id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/40">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">{s.name}</span>
                    <span className="rounded bg-muted px-1.5 text-[10px] font-medium text-muted-foreground">{s.tier}</span>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">
                    {s.unresolved_findings} unresolved · {s.critical_findings} critical
                    {s.top_finding ? ` · top: ${s.top_finding.ref}` : ""}
                  </div>
                </div>
                <div className="w-28">
                  <div className="mb-0.5 flex justify-between text-[10px] text-muted-foreground">
                    <span>{s.exposure_level}</span>
                    <span className="font-semibold text-foreground tabular-nums">{s.exposure_index}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted">
                    <div className="h-1.5 rounded-full" style={{ width: `${s.exposure_index}%`, backgroundColor: scoreColor(s.exposure_index) }} />
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

function CriticalAttention({ data }: { data: DashboardSummary["critical_attention"] }) {
  const router = useRouter();
  return (
    <SectionCard
      title="Requires attention"
      description="Highest-priority unresolved findings by explainable risk score"
      actions={
        <Link href="/findings?view=unresolved" className="text-xs font-medium text-blue-700 hover:underline">
          All findings
        </Link>
      }
      bodyClassName="p-0"
    >
      {data.length === 0 ? (
        <EmptyState title="No unresolved findings" />
      ) : (
        <ul className="divide-y">
          {data.map((f) => (
            <li
              key={f.id}
              className="flex cursor-pointer items-start gap-3 px-4 py-2.5 hover:bg-muted/40"
              onClick={() => router.push(`/findings/${f.id}`)}
            >
              <ScorePill score={f.risk_score} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{f.title}</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                  <span className="mono">{f.ref}</span>
                  <span>·</span>
                  <span>{f.control_id}</span>
                  <span>·</span>
                  <span>{f.assigned_owner?.full_name ?? "Unassigned"}</span>
                  {f.overdue && <span className="font-semibold text-red-600">· Overdue (due {formatDate(f.due_date)})</span>}
                </div>
              </div>
              <div className="flex flex-col items-end gap-1">
                <SeverityBadge severity={f.severity} />
                <FindingStatusBadge status={f.status} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

function ExecutiveSummary() {
  const { data, isFetching, error, refetch } = useQuery({
    queryKey: ["executive-summary"],
    queryFn: () => api<IntelAnswer>("/intelligence/executive-summary", { method: "POST" }),
    staleTime: 60_000,
  });
  return (
    <SectionCard
      title={
        <span className="flex items-center gap-1.5">
          <Sparkles className="size-4 text-violet-500" /> Executive risk summary
        </span>
      }
      description="Derived only from stored assessment, finding and remediation records"
      actions={
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? <Spinner className="size-3.5" /> : <RefreshCw className="size-3.5" />} Refresh
        </Button>
      }
    >
      {error ? <ErrorState error={error} /> : !data ? <LoadingBlock rows={5} /> : <IntelAnswerView answer={data} compact />}
    </SectionCard>
  );
}

export default function OverviewPage() {
  const can = useCan();
  const run = useRunAssessment();
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardSummary>("/dashboard/summary"),
  });

  const k = data?.kpis;
  return (
    <div>
      <PageHeader
        eyebrow="Alpha Beta Bank"
        title="Executive Overview"
        description="Continuous view of technology control effectiveness, prioritised findings and potential business-service exposure. All figures are calculated from stored assessment records."
        actions={
          <>
            {data?.last_assessment && (
              <span className="mr-1 hidden text-xs text-muted-foreground md:inline">
                <Clock className="mr-1 inline size-3.5" />
                {data.last_assessment.ref} · {relativeTime(data.last_assessment.evaluated_at)}
              </span>
            )}
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={cn("size-3.5", isFetching && "animate-spin")} /> Refresh
            </Button>
            {can(PERM.ASSESSMENTS_RUN) && (
              <Button size="sm" onClick={() => run.mutate(undefined)} disabled={run.isPending}>
                {run.isPending ? <Spinner className="size-3.5" /> : <Play className="size-3.5" />} Run Control Assessment
              </Button>
            )}
          </>
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : isLoading || !k ? (
        <LoadingBlock rows={10} />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiCard
              label="Control effectiveness"
              value={`${k.effectiveness_rate}%`}
              sub={`${k.effective_controls} of ${k.total_control_instances - k.not_assessed_controls} assessed instances effective`}
              icon={CheckCircle2}
              tone={k.effectiveness_rate >= 90 ? "success" : k.effectiveness_rate >= 75 ? "warning" : "danger"}
              href="/controls"
            />
            <KpiCard
              label="Controls monitored"
              value={k.total_control_instances}
              sub={`${k.control_definitions} control definitions across ${k.total_control_instances} asset scopes`}
              icon={Activity}
              href="/controls"
            />
            <KpiCard
              label="Failed control instances"
              value={k.failed_controls}
              sub={`${k.control_definitions_failing} of ${k.control_definitions} controls have at least one failure`}
              icon={ShieldX}
              tone={k.failed_controls ? "danger" : "success"}
              href="/controls?status=Ineffective"
            />
            <KpiCard
              label="Needs review"
              value={k.needs_review_controls}
              sub="Missing, stale or invalid evidence"
              icon={FileWarning}
              tone={k.needs_review_controls ? "warning" : "success"}
              href="/controls?status=Needs%20Review"
            />
            <KpiCard
              label="Critical findings"
              value={k.critical_findings}
              sub={`${k.unresolved_findings} unresolved findings in total`}
              icon={AlertOctagon}
              tone={k.critical_findings ? "danger" : "success"}
              href="/findings?severity=Critical&view=unresolved"
            />
            <KpiCard
              label="Overdue remediation"
              value={k.overdue_findings}
              sub={`Findings past due date · ${k.overdue_remediation_actions} of ${k.open_remediation_actions} open actions overdue`}
              icon={Clock}
              tone={k.overdue_findings ? "danger" : "success"}
              href="/findings?view=overdue"
            />
            <KpiCard
              label="Services with potential exposure"
              value={`${k.services_at_risk} / ${k.services_total}`}
              sub="Unresolved High/Critical finding in dependency path"
              icon={Network}
              tone={k.services_at_risk ? "warning" : "success"}
              href="/services"
            />
            <KpiCard
              label="Risk-accepted findings"
              value={k.risk_accepted_findings}
              sub="Time-bound acceptances with accountable approver"
              icon={ArrowRight}
              href="/findings?status=Risk%20Accepted"
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <TrendChart />
            </div>
            <SeverityChart data={data.severity_distribution} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <CriticalAttention data={data.critical_attention} />
            <ServicesAtRisk data={data.services_at_risk} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <DomainChart data={data.domain_distribution} />
            <ExecutiveSummary />
          </div>
        </div>
      )}
    </div>
  );
}
