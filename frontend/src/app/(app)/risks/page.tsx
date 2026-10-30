"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorState, PageHeader, ScorePill, SectionCard, SeverityBadge } from "@/components/common";
import { DataTable } from "@/components/data-table";
import { RiskFormDialog, type RiskSummary } from "@/components/risk-form";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useCan, useMeta } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

export default function RisksPage() {
  const router = useRouter();
  const can = useCan();
  const meta = useMeta();
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["risks", category, status],
    queryFn: () => api<RiskSummary[]>("/risks", { params: { category, status } }),
  });

  const columns = useMemo<ColumnDef<RiskSummary, unknown>[]>(
    () => [
      {
        accessorKey: "id",
        header: "Risk",
        cell: ({ row }) => (
          <div className="max-w-md min-w-64 whitespace-normal">
            <div className="mono text-xs font-semibold text-blue-700">{row.original.id}</div>
            <div className="font-medium">{row.original.title}</div>
          </div>
        ),
      },
      { accessorKey: "category", header: "Category", cell: ({ getValue }) => <span className="text-xs">{getValue() as string}</span> },
      {
        id: "owner",
        header: "Owner",
        accessorFn: (r) => r.owner?.full_name ?? "",
        cell: ({ getValue }) => <span className="text-xs">{(getValue() as string) || "—"}</span>,
      },
      { accessorKey: "inherent_rating", header: "Inherent", cell: ({ getValue }) => <SeverityBadge severity={getValue() as string} /> },
      { accessorKey: "residual_rating", header: "Residual", cell: ({ getValue }) => <SeverityBadge severity={getValue() as string} /> },
      {
        id: "controls",
        header: "Controls",
        accessorFn: (r) => r.control_ids.length,
        cell: ({ row }) => <span className="mono text-[11px]">{row.original.control_ids.join(", ")}</span>,
      },
      {
        accessorKey: "active_finding_count",
        header: "Active findings",
        cell: ({ row }) => (
          <span className="flex items-center gap-2">
            <span className="tabular-nums">
              {row.original.active_finding_count}/{row.original.finding_count}
            </span>
            {row.original.max_active_score > 0 && <ScorePill score={row.original.max_active_score} />}
          </span>
        ),
      },
      { accessorKey: "treatment", header: "Treatment", cell: ({ getValue }) => <span className="text-xs">{getValue() as string}</span> },
      { accessorKey: "status", header: "Status", cell: ({ getValue }) => <span className="text-xs">{getValue() as string}</span> },
      { accessorKey: "review_date", header: "Next review", cell: ({ getValue }) => <span className="text-xs whitespace-nowrap">{formatDate(getValue() as string)}</span> },
    ],
    [],
  );

  return (
    <div>
      <PageHeader
        title="Risk Register"
        description="Technology risks traced to the controls that mitigate them, the latest assessments and evidence for those controls, and the findings and remediation in flight."
        actions={
          can(PERM.RISKS_WRITE) && (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="size-3.5" /> Register risk
            </Button>
          )
        }
      />
      <SectionCard
        bodyClassName="p-0"
        title="Technology risks"
        actions={
          <div className="flex gap-2">
            <SimpleSelect value={category} onChange={setCategory} options={meta.data?.risk_categories ?? []} allLabel="All categories" />
            <SimpleSelect value={status} onChange={setStatus} options={meta.data?.risk_statuses ?? []} allLabel="All statuses" />
          </div>
        }
      >
        {error ? (
          <div className="p-4">
            <ErrorState error={error} onRetry={() => refetch()} />
          </div>
        ) : (
          <DataTable columns={columns} data={data ?? []} loading={isLoading} onRowClick={(r) => router.push(`/risks/${r.id}`)} emptyTitle="No risks match these filters" />
        )}
      </SectionCard>
      {creating && <RiskFormDialog open onOpenChange={setCreating} onSaved={(id) => id && router.push(`/risks/${id}`)} />}
    </div>
  );
}
