"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { History, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingBlock, PageHeader, RefLink, SectionCard, Spinner, StatusBadge } from "@/components/common";
import { DataTable } from "@/components/data-table";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { STATUS_COLORS, formatDateTime, relativeTime } from "@/lib/format";
import { useCan, useMeta, useRunAssessment } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { ControlItem, ControlStatus, Page, Run } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUSES: ControlStatus[] = ["Effective", "Ineffective", "Needs Review", "Not Assessed"];

function InstanceBar({ counts, total }: { counts: Partial<Record<ControlStatus, number>>; total: number }) {
  return (
    <div className="w-40">
      <div className="flex h-2 overflow-hidden rounded-full bg-muted">
        {STATUSES.map((s) =>
          counts[s] ? (
            <div key={s} title={`${s}: ${counts[s]}`} style={{ width: `${((counts[s] ?? 0) / total) * 100}%`, backgroundColor: STATUS_COLORS[s] }} />
          ) : null,
        )}
      </div>
      <div className="mt-1 text-[11px] text-muted-foreground tabular-nums">
        {counts.Effective ?? 0}/{total} effective
        {counts.Ineffective ? <span className="text-red-600"> · {counts.Ineffective} failed</span> : null}
        {counts["Needs Review"] ? <span className="text-amber-600"> · {counts["Needs Review"]} review</span> : null}
      </div>
    </div>
  );
}

function RunHistory({ selected }: { selected: string | null }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["runs", "recent"],
    queryFn: () => api<Page<Run>>("/assessments/runs", { params: { page_size: 12 } }),
  });
  return (
    <SectionCard
      title={
        <span className="flex items-center gap-1.5">
          <History className="size-4" /> Assessment runs
        </span>
      }
      description="Every run is recorded; assessments within a run are immutable"
      bodyClassName="p-0"
    >
      {error ? (
        <div className="p-4">
          <ErrorState error={error} />
        </div>
      ) : isLoading ? (
        <LoadingBlock className="p-4" />
      ) : (
        <ul className="divide-y">
          {data?.items.map((r) => {
            const s = r.summary;
            const active = selected === String(r.id) || selected === r.ref;
            return (
              <li key={r.id} className={cn("px-4 py-2.5 text-xs", active && "bg-blue-50/70")}>
                <div className="flex items-center justify-between gap-2">
                  <Link href={`/controls?run=${r.id}`} scroll={false} className="mono font-semibold text-blue-700 hover:underline">
                    {r.ref}
                  </Link>
                  <span className="text-muted-foreground">{relativeTime(r.evaluated_at)}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-2 text-muted-foreground">
                  <span className="capitalize">{r.trigger}</span>
                  <span>· {r.triggered_by ?? "system"}</span>
                  <span>· {s.scopes_evaluated} instances</span>
                  <span>· {s.duration_ms} ms</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-2 tabular-nums">
                  <span className="text-emerald-700">{s.results.Effective ?? 0} effective</span>
                  <span className="text-red-700">{s.results.Ineffective ?? 0} ineffective</span>
                  <span className="text-amber-700">{s.results["Needs Review"] ?? 0} review</span>
                </div>
                {active && (
                  <div className="mt-2 space-y-1.5 rounded-md border bg-background p-2">
                    <div>
                      <span className="font-medium">Evaluated:</span> {formatDateTime(r.evaluated_at)} · {r.scope_description}
                    </div>
                    {s.status_changes.length > 0 ? (
                      <div>
                        <div className="font-medium">Status changes</div>
                        <ul className="mt-0.5 space-y-0.5">
                          {s.status_changes.map((c, i) => (
                            <li key={i}>
                              <Link href={`/controls/${c.control_id}`} className="mono text-blue-700 hover:underline">
                                {c.control_id}
                              </Link>{" "}
                              on <span className="mono">{c.asset_id}</span>: {c.from} → {c.to}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <div className="text-muted-foreground">No status changes compared with the previous run.</div>
                    )}
                    {[
                      ["Findings created", s.findings_created],
                      ["Findings resolved", s.findings_resolved],
                      ["Pending validation", s.findings_pending_validation],
                      ["Findings reopened", s.findings_reopened],
                    ].map(([label, refs]) =>
                      (refs as string[]).length ? (
                        <div key={label as string}>
                          <span className="font-medium">{label as string}:</span>{" "}
                          {(refs as string[]).map((ref) => (
                            <Link key={ref} href={`/findings/${ref}`} className="mono mr-1.5 text-blue-700 hover:underline">
                              {ref}
                            </Link>
                          ))}
                        </div>
                      ) : null,
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}

function ControlsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const status = params.get("status") ?? "";
  const domain = params.get("domain") ?? "";
  const runParam = params.get("run");
  const can = useCan();
  const meta = useMeta();
  const run = useRunAssessment();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["controls", status, domain],
    queryFn: () => api<ControlItem[]>("/controls", { params: { status, domain } }),
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`/controls${next.toString() ? `?${next}` : ""}`, { scroll: false });
  };

  const columns = useMemo<ColumnDef<ControlItem, unknown>[]>(
    () => [
      {
        accessorKey: "id",
        header: "Control",
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="mono text-xs font-semibold text-blue-700">{row.original.id}</div>
            <div className="font-medium">{row.original.name}</div>
          </div>
        ),
      },
      { accessorKey: "domain", header: "Domain", cell: ({ getValue }) => <span className="text-xs">{getValue() as string}</span> },
      {
        id: "owner",
        header: "Owner",
        accessorFn: (c) => c.owner?.full_name ?? "",
        cell: ({ getValue }) => <span className="text-xs">{(getValue() as string) || "—"}</span>,
      },
      { accessorKey: "frequency", header: "Frequency", cell: ({ getValue }) => <span className="text-xs">{getValue() as string}</span> },
      {
        id: "instances",
        header: "Asset scopes",
        accessorFn: (c) => c.scope_count ?? 0,
        cell: ({ row }) => <InstanceBar counts={row.original.status_counts ?? {}} total={row.original.scope_count ?? 0} />,
      },
      { accessorKey: "current_status", header: "Status", cell: ({ getValue }) => <StatusBadge status={getValue() as string} /> },
      {
        accessorKey: "open_findings",
        header: "Open findings",
        cell: ({ getValue }) => <span className={cn("tabular-nums", (getValue() as number) > 0 && "font-semibold text-red-600")}>{getValue() as number}</span>,
      },
      {
        accessorKey: "last_assessed_at",
        header: "Last assessed",
        cell: ({ row }) => (
          <div className="text-xs">
            <div>{relativeTime(row.original.last_assessed_at)}</div>
            <div className="text-muted-foreground">rule v{row.original.rule_version}</div>
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <div>
      <PageHeader
        title="Control Monitoring"
        description="Automated controls are evaluated against the latest evidence for every in-scope asset. Missing or stale evidence yields Needs Review — never an assumed pass."
        actions={
          can(PERM.ASSESSMENTS_RUN) && (
            <Button size="sm" onClick={() => run.mutate(undefined)} disabled={run.isPending}>
              {run.isPending ? <Spinner className="size-3.5" /> : <Play className="size-3.5" />} Run Control Assessment
            </Button>
          )
        }
      />
      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <SectionCard
          title="Control library"
          description="Status is the worst outcome across the control's asset scopes"
          bodyClassName="p-0"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <SimpleSelect value={status} onChange={(v) => setParam("status", v)} options={STATUSES} allLabel="All statuses" />
              <SimpleSelect
                value={domain}
                onChange={(v) => setParam("domain", v)}
                options={meta.data?.control_domains ?? []}
                allLabel="All domains"
                className="min-w-48"
              />
            </div>
          }
        >
          {error ? (
            <div className="p-4">
              <ErrorState error={error} onRetry={() => refetch()} />
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={data ?? []}
              loading={isLoading}
              onRowClick={(c) => router.push(`/controls/${c.id}`)}
              emptyTitle="No controls match these filters"
            />
          )}
        </SectionCard>
        <RunHistory selected={runParam} />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Looking for a specific record? Individual assessments are linked from each control&apos;s detail page, e.g.{" "}
        <RefLink href="/controls/CTRL-IAM-001">CTRL-IAM-001</RefLink>.
      </p>
    </div>
  );
}

export default function ControlsPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <ControlsInner />
    </Suspense>
  );
}
