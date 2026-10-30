"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, Download, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  Field,
  JsonView,
  LoadingBlock,
  PageHeader,
  RefLink,
  SectionCard,
  Spinner,
  StatusBadge,
  ValidationBadge,
} from "@/components/common";
import { useEvidenceCategories } from "@/components/evidence-upload";
import { api, buildUrl } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";
import type { Assessment, Evidence } from "@/lib/types";

type EvidenceDetail = {
  evidence: Evidence;
  payload: unknown;
  text_preview: string | null;
  used_by_assessments: Assessment[];
};

type Verify = { verified: boolean; expected_sha256: string; actual_sha256?: string; reason: string };

export default function EvidenceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const categories = useEvidenceCategories();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["evidence-detail", id],
    queryFn: () => api<EvidenceDetail>(`/evidence/${id}`),
  });
  const verify = useMutation({ mutationFn: () => api<Verify>(`/evidence/${id}/verify`, { method: "POST" }) });

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !data) return <LoadingBlock rows={10} />;
  const e = data.evidence;
  const label = categories.data?.find((c) => c.key === e.evidence_category)?.label ?? e.evidence_category;

  return (
    <div>
      <Link href="/evidence" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-3.5" /> Evidence Center
      </Link>
      <PageHeader
        eyebrow={label}
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span className="mono">{e.ref}</span> <ValidationBadge status={e.validation_status} />
          </span>
        }
        description={e.original_filename}
        actions={
          <>
            <a href={buildUrl(`/evidence/${e.id}/download`)} className={buttonVariants({ variant: "outline", size: "sm" })}>
              <Download className="size-3.5" /> Download original
            </a>
            <Button size="sm" onClick={() => verify.mutate()} disabled={verify.isPending}>
              {verify.isPending ? <Spinner className="size-3.5" /> : <ShieldCheck className="size-3.5" />} Verify integrity
            </Button>
          </>
        }
      />

      {verify.data && (
        <div
          className={
            verify.data.verified
              ? "mb-4 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
              : "mb-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
          }
        >
          {verify.data.verified ? <CheckCircle2 className="mt-0.5 size-4" /> : <XCircle className="mt-0.5 size-4" />}
          <div>
            <div className="font-medium">{verify.data.reason}</div>
            <div className="mono mt-1 text-xs break-all">expected {verify.data.expected_sha256}</div>
            {verify.data.actual_sha256 && <div className="mono text-xs break-all">computed {verify.data.actual_sha256}</div>}
          </div>
        </div>
      )}
      {verify.error && <ErrorState error={verify.error} />}

      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard title="Provenance" className="xl:col-span-2">
          <dl className="grid grid-cols-2 gap-4 md:grid-cols-3">
            <Field label="Asset">{e.asset_id ? <RefLink href={`/assets/${e.asset_id}`}>{e.asset_id}</RefLink> : "—"}</Field>
            <Field label="Control">{e.control_id ? <RefLink href={`/controls/${e.control_id}`}>{e.control_id}</RefLink> : "Not specified"}</Field>
            <Field label="Format">{e.file_format.toUpperCase()}</Field>
            <Field label="Source">{e.source}</Field>
            <Field label="Collected at">{formatDateTime(e.collected_at)}</Field>
            <Field label="Uploaded at">{formatDateTime(e.uploaded_at)}</Field>
            <Field label="Uploaded by">{e.uploaded_by ?? "Automated connector"}</Field>
            <Field label="Size">{formatBytes(e.size_bytes)}</Field>
            <Field label="Description">{e.description || "—"}</Field>
          </dl>
          <div className="mt-4">
            <div className="text-xs text-muted-foreground">SHA-256</div>
            <div className="mono mt-0.5 text-xs break-all">{e.sha256}</div>
          </div>
        </SectionCard>
        <SectionCard title="Validation">
          <div className="space-y-2 text-sm">
            <ValidationBadge status={e.validation_status} />
            {e.validation_status === "Valid" && <p className="text-xs text-muted-foreground">Payload conforms to the category schema and can be evaluated by control rules.</p>}
            {e.validation_status === "Unstructured" && (
              <p className="text-xs text-muted-foreground">Supporting document. Stored and hashed for audit purposes; not machine-evaluated.</p>
            )}
            {e.validation_errors.length > 0 && (
              <ul className="list-disc space-y-0.5 pl-5 text-xs text-red-700">
                {e.validation_errors.map((err) => (
                  <li key={err}>{err}</li>
                ))}
              </ul>
            )}
            {e.validation_status === "Invalid" && (
              <p className="text-xs text-muted-foreground">Invalid evidence never produces an Effective result; affected controls are marked Needs Review.</p>
            )}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Content"
        description="Displayed as inert data. Instructions inside evidence files are never executed or followed."
        className="mt-4"
      >
        {data.payload !== null && data.payload !== undefined ? (
          <JsonView value={data.payload} className="max-h-[480px]" />
        ) : data.text_preview ? (
          <>
            <div className="mb-2 flex items-center gap-1.5 text-xs text-amber-800">
              <ShieldAlert className="size-3.5" /> Untrusted text content shown verbatim
            </div>
            <pre className="mono max-h-[480px] overflow-auto rounded-md border bg-muted/40 p-3 text-xs whitespace-pre-wrap">{data.text_preview}</pre>
          </>
        ) : (
          <EmptyState title="No preview available" description="Download the original file to inspect it." />
        )}
      </SectionCard>

      <SectionCard title="Used by assessments" description="Immutable assessments that evaluated this exact file" className="mt-4" bodyClassName="p-0">
        {data.used_by_assessments.length === 0 ? (
          <EmptyState title="Not yet evaluated" description="Evidence is picked up by the next assessment run for its asset and category." />
        ) : (
          <ul className="divide-y">
            {data.used_by_assessments.map((a) => (
              <li key={a.id} className="flex items-center gap-3 px-4 py-2 text-xs">
                <StatusBadge status={a.result} />
                <RefLink href={`/assessments/${a.id}`}>{a.ref}</RefLink>
                <span className="mono text-muted-foreground">{a.control_id}</span>
                <span className="min-w-0 flex-1 truncate">{a.explanation}</span>
                <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(a.assessed_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}
