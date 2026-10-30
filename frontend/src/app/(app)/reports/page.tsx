"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileDown, FileText } from "lucide-react";
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, SectionCard, Spinner } from "@/components/common";
import { SimpleSelect } from "@/components/simple-select";
import { ApiError, api, buildUrl } from "@/lib/api";
import { formatDateTime, shortHash } from "@/lib/format";
import { useCan } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import { cn } from "@/lib/utils";

type ReportType = { key: string; title: string };

type Section =
  | { key: string; title: string; note: string | null; kind: "kpis"; items: { label: string; value: string }[] }
  | { key: string; title: string; note: string | null; kind: "bullets"; items: string[] }
  | { key: string; title: string; note: string | null; kind: "trend"; points: { label: string; value: number }[] }
  | { key: string; title: string; note: string | null; kind: "table"; columns: string[]; rows: string[][] };

type Report = {
  type: string;
  title: string;
  organization: string;
  generated_at: string;
  generated_by: string;
  period: { days: number; start: string; end: string };
  disclaimer: string;
  sections: Section[];
};

type HistoryItem = {
  id: number;
  ref: string;
  report_type: string;
  title: string;
  period_days: number;
  generated_at: string;
  generated_by: string | null;
  sha256: string;
};

const DESCRIPTIONS: Record<string, string> = {
  executive_summary: "Board-level view of control effectiveness, priority findings and service exposure.",
  control_effectiveness: "Status of every control definition and the evidence behind each exception.",
  critical_findings: "Active Critical and High findings with impact and evidence references.",
  remediation_aging: "Age profile, opened-vs-resolved flow, open actions and risk acceptances.",
  business_services: "Potential exposure ranking and single points of failure by service.",
};

const PERIODS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
  { value: "180", label: "Last 180 days" },
  { value: "365", label: "Last 12 months" },
];

function SectionView({ s }: { s: Section }) {
  return (
    <div className="space-y-2">
      <div>
        <h3 className="text-sm font-semibold">{s.title}</h3>
        {s.note && <p className="text-xs text-muted-foreground">{s.note}</p>}
      </div>
      {s.kind === "kpis" && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {s.items.map((k) => (
            <div key={k.label} className="rounded-lg border p-2.5">
              <div className="text-[11px] text-muted-foreground">{k.label}</div>
              <div className="text-lg font-semibold tabular-nums">{k.value}</div>
            </div>
          ))}
        </div>
      )}
      {s.kind === "bullets" && (
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {s.items.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      )}
      {s.kind === "trend" &&
        (s.points.length < 2 ? (
          <p className="text-xs text-muted-foreground">Insufficient assessment history in this period.</p>
        ) : (
          <div className="h-48">
            <ResponsiveContainer>
              <LineChart data={s.points} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={20} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                <ChartTooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Line type="monotone" dataKey="value" name="Effectiveness %" stroke="#1e3a8a" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ))}
      {s.kind === "table" &&
        (s.rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">No records.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  {s.columns.map((c) => (
                    <TableHead key={c} className="h-8 text-xs">
                      {c}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {s.rows.map((r, i) => (
                  <TableRow key={i}>
                    {r.map((v, j) => (
                      <TableCell key={j} className="max-w-sm py-1.5 text-xs whitespace-normal">
                        {v}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))}
    </div>
  );
}

async function downloadPdf(type: string, period: string): Promise<string> {
  const res = await fetch(buildUrl(`/reports/${type}/pdf`, { period_days: period }), { credentials: "same-origin" });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = disposition.match(/filename="?([^";]+)"?/)?.[1] ?? `${type}.pdf`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  return filename;
}

export default function ReportsPage() {
  const can = useCan();
  const qc = useQueryClient();
  const [type, setType] = useState("executive_summary");
  const [period, setPeriod] = useState("30");
  const types = useQuery({ queryKey: ["report-types"], queryFn: () => api<ReportType[]>("/reports/types") });
  const history = useQuery({ queryKey: ["report-history"], queryFn: () => api<HistoryItem[]>("/reports/history") });
  const allowed = can(PERM.REPORTS);
  const preview = useQuery({
    queryKey: ["report", type, period],
    queryFn: () => api<Report>(`/reports/${type}`, { params: { period_days: period } }),
    enabled: allowed,
  });
  const pdf = useMutation({
    mutationFn: () => downloadPdf(type, period),
    onSuccess: (name) => {
      toast.success("PDF generated", { description: name });
      qc.invalidateQueries({ queryKey: ["report-history"] });
    },
    onError: (e: Error) => toast.error("PDF generation failed", { description: e.message }),
  });

  return (
    <div>
      <PageHeader
        title="Reports"
        description="Reports are generated on demand from stored records. Each PDF is fingerprinted with SHA-256 and recorded in the report history."
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {(types.data ?? []).map((t) => (
          <button
            key={t.key}
            onClick={() => setType(t.key)}
            className={cn("rounded-xl border bg-card p-3 text-left transition-shadow hover:shadow-md", type === t.key && "ring-2 ring-primary")}
          >
            <FileText className="size-4 text-blue-700" />
            <div className="mt-1.5 text-sm font-semibold">{t.title}</div>
            <p className="mt-0.5 text-xs text-muted-foreground">{DESCRIPTIONS[t.key]}</p>
          </button>
        ))}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_340px]">
        <SectionCard
          title={preview.data?.title ?? "Preview"}
          description={
            preview.data
              ? `${preview.data.organization} · generated ${formatDateTime(preview.data.generated_at)} by ${preview.data.generated_by}`
              : undefined
          }
          actions={
            <div className="flex items-center gap-2">
              <SimpleSelect value={period} onChange={setPeriod} options={PERIODS} />
              <Button size="sm" onClick={() => pdf.mutate()} disabled={!allowed || pdf.isPending}>
                {pdf.isPending ? <Spinner className="size-3.5" /> : <FileDown className="size-3.5" />} Export PDF
              </Button>
            </div>
          }
        >
          {!allowed ? (
            <EmptyState title="Your role cannot generate reports" />
          ) : preview.error ? (
            <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
          ) : preview.isLoading || !preview.data ? (
            <LoadingBlock rows={10} />
          ) : (
            <div className="space-y-6">
              {preview.data.sections.map((s) => (
                <SectionView key={s.key} s={s} />
              ))}
              <p className="border-t pt-3 text-[11px] text-muted-foreground">{preview.data.disclaimer}</p>
            </div>
          )}
        </SectionCard>
        <SectionCard title="Report history" bodyClassName="p-0">
          {history.isLoading ? (
            <LoadingBlock className="p-4" />
          ) : (history.data ?? []).length === 0 ? (
            <EmptyState title="No reports generated yet" />
          ) : (
            <ul className="divide-y">
              {history.data!.map((h) => (
                <li key={h.id} className="px-4 py-2.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="mono font-semibold">{h.ref}</span>
                    <span className="text-muted-foreground">{formatDateTime(h.generated_at)}</span>
                  </div>
                  <div className="mt-0.5">{h.title}</div>
                  <div className="text-muted-foreground">
                    {h.period_days} days · {h.generated_by ?? "—"}
                  </div>
                  <div className="mono text-[10px] text-muted-foreground" title={h.sha256}>
                    sha256 {shortHash(h.sha256, 20)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
