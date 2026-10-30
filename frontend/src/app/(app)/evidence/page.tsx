"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Search, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState, LoadingBlock, PageHeader, Pagination, SectionCard, ValidationBadge } from "@/components/common";
import { DataTable } from "@/components/data-table";
import { EvidenceUploadDialog, useEvidenceCategories } from "@/components/evidence-upload";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { formatBytes, formatDateTime, shortHash } from "@/lib/format";
import { useCan } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { Evidence, Page } from "@/lib/types";

const PAGE_SIZE = 25;

function EvidenceInner() {
  const router = useRouter();
  const params = useSearchParams();
  const can = useCan();
  const categories = useEvidenceCategories();
  const [q, setQ] = useState(params.get("q") ?? "");
  const uploadOpen = params.get("upload") === "1";
  const category = params.get("category") ?? "";
  const validation = params.get("validation_status") ?? "";
  const uploadedOnly = params.get("uploaded_only") === "true";
  const page = Number(params.get("page") ?? 1);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in changes)) next.delete("page");
    router.replace(`/evidence${next.toString() ? `?${next}` : ""}`, { scroll: false });
  };

  useEffect(() => {
    const t = setTimeout(() => {
      if ((params.get("q") ?? "") !== q) update({ q });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["evidence", { category, validation, uploadedOnly, page, q: params.get("q") }],
    queryFn: () =>
      api<Page<Evidence>>("/evidence", {
        params: {
          q: params.get("q"),
          category,
          validation_status: validation,
          uploaded_only: uploadedOnly || undefined,
          page,
          page_size: PAGE_SIZE,
        },
      }),
    placeholderData: keepPreviousData,
  });

  const labels = useMemo(() => new Map((categories.data ?? []).map((c) => [c.key, c.label])), [categories.data]);

  const columns = useMemo<ColumnDef<Evidence, unknown>[]>(
    () => [
      {
        accessorKey: "ref",
        header: "Evidence",
        cell: ({ row }) => (
          <div className="max-w-sm min-w-56">
            <div className="mono text-xs font-semibold text-blue-700">{row.original.ref}</div>
            <div className="truncate text-xs">{row.original.original_filename}</div>
          </div>
        ),
      },
      {
        accessorKey: "evidence_category",
        header: "Category",
        cell: ({ getValue }) => <span className="text-xs">{labels.get(getValue() as string) ?? (getValue() as string)}</span>,
      },
      { accessorKey: "asset_id", header: "Asset", cell: ({ getValue }) => <span className="mono text-xs">{(getValue() as string) ?? "—"}</span> },
      {
        accessorKey: "source",
        header: "Source",
        cell: ({ row }) => (
          <div className="max-w-56 text-xs">
            <div className="truncate">{row.original.source}</div>
            <div className="text-muted-foreground">{row.original.uploaded_by ? `uploaded by ${row.original.uploaded_by}` : "automated connector"}</div>
          </div>
        ),
      },
      { accessorKey: "validation_status", header: "Validation", cell: ({ getValue }) => <ValidationBadge status={getValue() as string} /> },
      {
        accessorKey: "collected_at",
        header: "Collected",
        cell: ({ getValue }) => <span className="text-xs whitespace-nowrap">{formatDateTime(getValue() as string)}</span>,
      },
      {
        accessorKey: "sha256",
        header: "SHA-256",
        cell: ({ row }) => (
          <span className="mono text-[11px] text-muted-foreground" title={row.original.sha256}>
            {shortHash(row.original.sha256)} · {formatBytes(row.original.size_bytes)}
          </span>
        ),
      },
    ],
    [labels],
  );

  return (
    <div>
      <PageHeader
        title="Evidence Center"
        description="Every evidence file is validated, hashed (SHA-256) and stored immutably. Assessments reference the exact evidence they evaluated."
        actions={
          can(PERM.EVIDENCE_UPLOAD) && (
            <Button size="sm" onClick={() => update({ upload: "1" })}>
              <Upload className="size-3.5" /> Upload evidence
            </Button>
          )
        }
      />
      <SectionCard bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
          <div className="relative">
            <Search className="absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search EVD-, file, asset, source, hash…" className="h-8 w-64 pl-7 text-sm" />
          </div>
          <SimpleSelect
            value={category}
            onChange={(v) => update({ category: v })}
            options={(categories.data ?? []).map((c) => ({ value: c.key, label: c.label }))}
            allLabel="All categories"
            className="min-w-48"
          />
          <SimpleSelect value={validation} onChange={(v) => update({ validation_status: v })} options={["Valid", "Invalid", "Unstructured"]} allLabel="Any validation" />
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={uploadedOnly} onChange={(e) => update({ uploaded_only: e.target.checked ? "true" : null })} /> Manual uploads only
          </label>
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
              onRowClick={(e) => router.push(`/evidence/${e.id}`)}
              emptyTitle="No evidence matches these filters"
            />
            <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPage={(p) => update({ page: String(p) })} />
          </>
        )}
      </SectionCard>
      {uploadOpen && can(PERM.EVIDENCE_UPLOAD) && (
        <EvidenceUploadDialog
          open
          onOpenChange={(o) => !o && update({ upload: null, asset_id: null, control_id: null })}
          defaults={{ asset_id: params.get("asset_id") ?? undefined, control_id: params.get("control_id") ?? undefined }}
        />
      )}
    </div>
  );
}

export default function EvidencePage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <EvidenceInner />
    </Suspense>
  );
}
