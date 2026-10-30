"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { Globe, KeyRound, Plus, Search, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState, LoadingBlock, PageHeader, Pagination, SectionCard, SeverityBadge } from "@/components/common";
import { AssetFormDialog } from "@/components/asset-form";
import { DataTable } from "@/components/data-table";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useCan, useMeta } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { Asset, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;
const SORTABLE = new Set(["id", "name", "asset_type", "last_assessed_at"]);

function AssetsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const meta = useMeta();
  const can = useCan();
  const [creating, setCreating] = useState(false);
  const [q, setQ] = useState(params.get("q") ?? "");
  const filters = {
    asset_type: params.get("asset_type") ?? "",
    criticality: params.get("criticality") ?? "",
    environment: params.get("environment") ?? "",
    service_id: params.get("service_id") ?? "",
    internet_exposed: params.get("internet_exposed") ?? "",
  };
  const sort = params.get("sort") ?? "id";
  const page = Number(params.get("page") ?? 1);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in changes)) next.delete("page");
    router.replace(`/assets${next.toString() ? `?${next}` : ""}`, { scroll: false });
  };

  useEffect(() => {
    const t = setTimeout(() => {
      if ((params.get("q") ?? "") !== q) update({ q });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["assets", filters, sort, page, params.get("q")],
    queryFn: () =>
      api<Page<Asset>>("/assets", {
        params: { ...filters, q: params.get("q"), sort, page, page_size: PAGE_SIZE },
      }),
    placeholderData: keepPreviousData,
  });

  const sorting: SortingState = [{ id: sort.replace(/^-/, ""), desc: sort.startsWith("-") }];

  const columns = useMemo<ColumnDef<Asset, unknown>[]>(
    () => [
      {
        accessorKey: "id",
        header: "Asset",
        cell: ({ row }) => (
          <div>
            <div className="mono text-xs font-semibold text-blue-700">{row.original.id}</div>
            <div className="font-medium">{row.original.name}</div>
          </div>
        ),
      },
      { accessorKey: "asset_type", header: "Type", cell: ({ getValue }) => <span className="text-xs">{getValue() as string}</span> },
      {
        accessorKey: "criticality",
        header: "Criticality",
        enableSorting: false,
        cell: ({ getValue }) => <SeverityBadge severity={getValue() as string} />,
      },
      {
        id: "attrs",
        header: "Attributes",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex gap-1.5 text-muted-foreground">
            {row.original.internet_exposed && (
              <span title="Internet-facing" className="text-orange-600">
                <Globe className="size-4" />
              </span>
            )}
            {row.original.privileged_access_hub && (
              <span title="Privileged access hub" className="text-violet-600">
                <KeyRound className="size-4" />
              </span>
            )}
            {!row.original.has_redundancy && (
              <span title="No redundancy">
                <ShieldOff className="size-4" />
              </span>
            )}
          </div>
        ),
      },
      {
        id: "services",
        header: "Direct services",
        enableSorting: false,
        cell: ({ row }) => <span className="text-xs">{row.original.services?.join(", ") || "—"}</span>,
      },
      {
        accessorKey: "open_findings",
        header: "Active findings",
        enableSorting: false,
        cell: ({ getValue }) => (
          <span className={cn("tabular-nums", (getValue() as number) > 0 && "font-semibold text-red-600")}>{getValue() as number}</span>
        ),
      },
      {
        accessorKey: "technical_owner",
        header: "Technical owner",
        enableSorting: false,
        cell: ({ getValue }) => <span className="text-xs">{getValue() as string}</span>,
      },
      {
        accessorKey: "last_assessed_at",
        header: "Last assessed",
        cell: ({ getValue }) => <span className="text-xs whitespace-nowrap">{relativeTime(getValue() as string | null)}</span>,
      },
    ],
    [],
  );
  return (
    <div>
      <PageHeader
        title="Technology Assets"
        description="Inventory of applications, infrastructure and services in scope for continuous control monitoring."
        actions={
          can(PERM.ASSETS_WRITE) && (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="size-3.5" /> Register asset
            </Button>
          )
        }
      />
      <SectionCard bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
          <div className="relative">
            <Search className="absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search ID, name, owner, platform…" className="h-8 w-64 pl-7 text-sm" />
          </div>
          <SimpleSelect value={filters.asset_type} onChange={(v) => update({ asset_type: v })} options={meta.data?.asset_types ?? []} allLabel="All types" />
          <SimpleSelect value={filters.criticality} onChange={(v) => update({ criticality: v })} options={meta.data?.criticality ?? []} allLabel="Any criticality" />
          <SimpleSelect value={filters.environment} onChange={(v) => update({ environment: v })} options={meta.data?.environments ?? []} allLabel="All environments" />
          <SimpleSelect
            value={filters.service_id}
            onChange={(v) => update({ service_id: v })}
            options={(meta.data?.services ?? []).map((s) => ({ value: s.id, label: s.name }))}
            allLabel="Any service path"
            className="min-w-44"
          />
          <SimpleSelect
            value={filters.internet_exposed}
            onChange={(v) => update({ internet_exposed: v })}
            options={[
              { value: "true", label: "Internet-facing" },
              { value: "false", label: "Internal only" },
            ]}
            allLabel="Any exposure"
          />
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
              onSortingChange={(s) => {
                const first = s[0];
                update({ sort: first && SORTABLE.has(first.id) ? `${first.desc ? "-" : ""}${first.id}` : null });
              }}
              onRowClick={(a) => router.push(`/assets/${a.id}`)}
              emptyTitle="No assets match these filters"
            />
            <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPage={(p) => update({ page: String(p) })} />
          </>
        )}
      </SectionCard>
      <p className="mt-2 text-xs text-muted-foreground">
        “Any service path” includes every asset in the service&apos;s transitive dependency closure, not just directly linked assets.
      </p>
      {creating && <AssetFormDialog open onOpenChange={setCreating} onSaved={(a) => router.push(`/assets/${a.id}`)} />}
    </div>
  );
}

export default function AssetsPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <AssetsInner />
    </Suspense>
  );
}
