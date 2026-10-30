"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ErrorState,
  FindingStatusBadge,
  LoadingBlock,
  PageHeader,
  Pagination,
  ScorePill,
  SectionCard,
  SeverityBadge,
} from "@/components/common";
import { DataTable } from "@/components/data-table";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { SEVERITY_ORDER, formatDate } from "@/lib/format";
import { useMeta } from "@/lib/hooks";
import type { Finding, Page, UserRef } from "@/lib/types";
import { cn } from "@/lib/utils";

const VIEWS = [
  { value: "unresolved", label: "Unresolved" },
  { value: "active", label: "All active" },
  { value: "overdue", label: "Overdue" },
  { value: "all", label: "All" },
];
const SORTABLE = new Set(["risk_score", "detected_at", "due_date", "updated_at"]);
const PAGE_SIZE = 25;

type RemediationActionRow = {
  id: number;
  ref: string;
  title: string;
  status: string;
  due_date: string;
  owner: UserRef;
  finding: { id: number; ref: string; title: string; severity: string };
  overdue: boolean;
};

function ActionsPanel() {
  const [overdueOnly, setOverdueOnly] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ["remediation-actions", overdueOnly],
    queryFn: () => api<RemediationActionRow[]>("/remediation/actions", { params: { overdue: overdueOnly || undefined } }),
  });
  return (
    <SectionCard
      title="Remediation actions"
      description="Tracked work items; completing an action does not resolve a finding — only a passing reassessment does"
      bodyClassName="p-0"
      actions={
        <label className="flex items-center gap-1.5 text-xs">
          <input type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} /> Overdue only
        </label>
      }
    >
      {error ? (
        <div className="p-4">
          <ErrorState error={error} />
        </div>
      ) : isLoading ? (
        <LoadingBlock className="p-4" />
      ) : (
        <ul className="divide-y">
          {(data ?? []).map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              <span className="mono w-20 shrink-0 text-xs text-muted-foreground">{a.ref}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{a.title}</div>
                <div className="text-xs text-muted-foreground">
                  <Link href={`/findings/${a.finding.id}`} className="mono text-blue-700 hover:underline">
                    {a.finding.ref}
                  </Link>{" "}
                  · {a.owner?.full_name ?? "Unassigned"}
                </div>
              </div>
              <span className={cn("text-xs whitespace-nowrap", a.overdue && "font-semibold text-red-600")}>
                {a.overdue ? "Overdue · " : "Due "}
                {formatDate(a.due_date)}
              </span>
              <span className="w-24 text-right text-xs">{a.status}</span>
            </li>
          ))}
          {data?.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted-foreground">No remediation actions</li>}
        </ul>
      )}
    </SectionCard>
  );
}

function FindingsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const meta = useMeta();
  const view = params.get("view") ?? (params.get("status") ? "all" : "unresolved");
  const severity = params.getAll("severity");
  const status = params.get("status") ?? "";
  const serviceId = params.get("service_id") ?? "";
  const controlId = params.get("control_id") ?? "";
  const assetId = params.get("asset_id") ?? "";
  const sort = params.get("sort") ?? "-risk_score";
  const page = Number(params.get("page") ?? 1);
  const [q, setQ] = useState(params.get("q") ?? "");

  const update = (changes: Record<string, string | string[] | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      next.delete(k);
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x));
      else if (v) next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    router.replace(`/findings${next.toString() ? `?${next}` : ""}`, { scroll: false });
  };

  useEffect(() => {
    const t = setTimeout(() => {
      if ((params.get("q") ?? "") !== q) update({ q });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["findings", { view, severity, status, serviceId, controlId, assetId, sort, page, q: params.get("q") }],
    queryFn: () =>
      api<Page<Finding>>("/findings", {
        params: {
          view: view === "all" ? undefined : view,
          severity,
          status: status ? [status] : undefined,
          service_id: serviceId,
          control_id: controlId,
          asset_id: assetId,
          q: params.get("q"),
          sort,
          page,
          page_size: PAGE_SIZE,
        },
      }),
    placeholderData: keepPreviousData,
  });

  const sorting: SortingState = [{ id: sort.replace(/^-/, ""), desc: sort.startsWith("-") }];
  const onSortingChange = (s: SortingState) => {
    const first = s[0];
    if (!first || !SORTABLE.has(first.id)) return update({ sort: null });
    update({ sort: `${first.desc ? "-" : ""}${first.id}` });
  };

  const columns = useMemo<ColumnDef<Finding, unknown>[]>(
    () => [
      {
        accessorKey: "risk_score",
        header: "Score",
        cell: ({ getValue }) => <ScorePill score={getValue() as number} />,
      },
      {
        accessorKey: "title",
        header: "Finding",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="max-w-xl min-w-64 whitespace-normal">
            <div className="font-medium">{row.original.title}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              <span className="mono">{row.original.ref}</span> · {row.original.control_id} · {row.original.asset_id}
              {row.original.service_name ? ` · ${row.original.service_name}` : ""}
            </div>
          </div>
        ),
      },
      { accessorKey: "severity", header: "Severity", enableSorting: false, cell: ({ getValue }) => <SeverityBadge severity={getValue() as string} /> },
      { accessorKey: "status", header: "Status", enableSorting: false, cell: ({ getValue }) => <FindingStatusBadge status={getValue() as string} /> },
      {
        id: "owner",
        header: "Owner",
        enableSorting: false,
        accessorFn: (f) => f.assigned_owner?.full_name ?? "Unassigned",
        cell: ({ getValue }) => <span className="text-xs">{getValue() as string}</span>,
      },
      {
        accessorKey: "detected_at",
        header: "Detected",
        cell: ({ row }) => (
          <div className="text-xs whitespace-nowrap">
            {formatDate(row.original.detected_at)}
            <div className="text-muted-foreground">{row.original.age_days} days old</div>
          </div>
        ),
      },
      {
        accessorKey: "due_date",
        header: "Due",
        cell: ({ row }) => (
          <span className={cn("text-xs whitespace-nowrap", row.original.overdue && "font-semibold text-red-600")}>
            {formatDate(row.original.due_date)}
            {row.original.overdue && <div>Overdue</div>}
          </span>
        ),
      },
    ],
    [],
  );

  const hasFilters = severity.length || status || serviceId || controlId || assetId || params.get("q");

  return (
    <div>
      <PageHeader
        title="Findings & Remediation"
        description="Findings are created and resolved by the control engine. Owners remediate and request validation; resolution requires a passing reassessment against updated evidence."
      />
      <Tabs value={view} onValueChange={(v) => update({ view: String(v), status: null })} className="mb-3">
        <TabsList>
          {VIEWS.map((v) => (
            <TabsTrigger key={v.value} value={v.value} className="px-3">
              {v.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <SectionCard bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
          <div className="relative">
            <Search className="absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, asset, control, FND-…" className="h-8 w-64 pl-7 text-sm" />
          </div>
          <div className="flex items-center gap-1">
            {SEVERITY_ORDER.map((s) => {
              const on = severity.includes(s);
              return (
                <button
                  key={s}
                  onClick={() => update({ severity: on ? severity.filter((x) => x !== s) : [...severity, s] })}
                  className={cn(
                    "rounded-md border px-2 py-1 text-xs font-medium",
                    on ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {s}
                </button>
              );
            })}
          </div>
          <SimpleSelect value={status} onChange={(v) => update({ status: v, view: v ? "all" : view })} options={meta.data?.finding_statuses ?? []} allLabel="Any status" />
          <SimpleSelect
            value={serviceId}
            onChange={(v) => update({ service_id: v })}
            options={(meta.data?.services ?? []).map((s) => ({ value: s.id, label: s.name }))}
            allLabel="All services"
            className="min-w-44"
          />
          <SimpleSelect
            value={controlId}
            onChange={(v) => update({ control_id: v })}
            options={(meta.data?.controls ?? []).map((c) => ({ value: c.id, label: `${c.id}` }))}
            allLabel="All controls"
          />
          {assetId && (
            <span className="inline-flex items-center gap-1 rounded-md border bg-muted px-2 py-1 text-xs">
              Asset {assetId}
              <button onClick={() => update({ asset_id: null })} aria-label="Clear asset filter">
                <X className="size-3" />
              </button>
            </span>
          )}
          {hasFilters ? (
            <button
              className="text-xs text-blue-700 hover:underline"
              onClick={() => {
                setQ("");
                router.replace(`/findings?view=${view}`);
              }}
            >
              Clear filters
            </button>
          ) : null}
          {isFetching && !isLoading && <span className="text-xs text-muted-foreground">Updating…</span>}
        </div>
        {error ? (
          <div className="p-4">
            <ErrorState error={error} onRetry={() => refetch()} />
          </div>
        ) : (
          <>
            <DataTable
              columns={columns}
              data={data?.items ?? []}
              loading={isLoading}
              manualSorting
              sorting={sorting}
              onSortingChange={onSortingChange}
              onRowClick={(f) => router.push(`/findings/${f.id}`)}
              emptyTitle="No findings match these filters"
              rowClassName={(f) => (f.overdue ? "bg-red-50/30" : undefined)}
            />
            <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPage={(p) => update({ page: String(p) })} />
          </>
        )}
      </SectionCard>
      <div className="mt-4">
        <ActionsPanel />
      </div>
    </div>
  );
}

export default function FindingsPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <FindingsInner />
    </Suspense>
  );
}
