"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, ChevronLeft, Network, Pencil } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  EmptyState,
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
} from "@/components/common";
import { AssetFormDialog } from "@/components/asset-form";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, relativeTime } from "@/lib/format";
import { useCan } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { Asset, Assessment, Finding, ServiceRef } from "@/lib/types";

type Dep = { id: string; name: string; asset_type: string; dependency_type: string };

type AssetDetail = {
  asset: Asset;
  direct_services: ServiceRef[];
  impacted_services: ServiceRef[];
  depends_on: Dep[];
  dependents: Dep[];
  controls: {
    control_id: string;
    control_name: string;
    domain: string;
    status: string;
    last_assessed_at: string | null;
    latest_assessment: Assessment | null;
  }[];
  findings: Finding[];
  assessment_history: Assessment[];
};

function DepList({ items, empty }: { items: Dep[]; empty: string }) {
  if (items.length === 0) return <p className="px-4 py-3 text-xs text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y">
      {items.map((d) => (
        <li key={d.id} className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
          <div className="min-w-0">
            <RefLink href={`/assets/${d.id}`}>{d.id}</RefLink> <span className="truncate">{d.name}</span>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">{d.dependency_type}</span>
        </li>
      ))}
    </ul>
  );
}

export default function AssetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const can = useCan();
  const [editing, setEditing] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["asset", id],
    queryFn: () => api<AssetDetail>(`/assets/${id}`),
  });

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !data) return <LoadingBlock rows={10} />;
  const a = data.asset;

  return (
    <div>
      <Link href="/assets" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-3.5" /> Technology Assets
      </Link>
      <PageHeader
        eyebrow={`${a.id} · ${a.asset_type}`}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {a.name} <SeverityBadge severity={a.criticality} />
          </span>
        }
        description={a.description}
        actions={
          <>
            <Link href={`/services?asset=${a.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
              <Network className="size-3.5" /> Dependency map
            </Link>
            {can(PERM.ASSETS_WRITE) && (
              <Button size="sm" onClick={() => setEditing(true)}>
                <Pencil className="size-3.5" /> Edit
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard title="Asset profile" className="xl:col-span-2">
          <dl className="grid grid-cols-2 gap-4 md:grid-cols-3">
            <Field label="Environment">{a.environment}</Field>
            <Field label="Lifecycle">{a.lifecycle_status}</Field>
            <Field label="Platform">{a.platform || "—"}</Field>
            <Field label="Business owner">{a.business_owner}</Field>
            <Field label="Technical owner">{a.technical_owner}</Field>
            <Field label="Last assessed">{formatDateTime(a.last_assessed_at)}</Field>
            <Field label="Internet-facing">{a.internet_exposed ? "Yes" : "No"}</Field>
            <Field label="Privileged access hub">{a.privileged_access_hub ? "Yes" : "No"}</Field>
            <Field label="Redundancy / failover">{a.has_redundancy ? "Yes" : "No — potential single point of failure"}</Field>
          </dl>
        </SectionCard>
        <SectionCard title="Business services" description="Services that would be exposed if this asset were compromised or unavailable">
          <div className="space-y-3 text-sm">
            <div>
              <div className="mb-1 text-xs text-muted-foreground">Direct support</div>
              {data.direct_services.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {data.direct_services.map((s) => (
                    <Link key={s.id} href={`/services/${s.id}`} className="rounded-md border px-2 py-0.5 text-xs hover:bg-muted">
                      {s.name}
                    </Link>
                  ))}
                </div>
              ) : (
                <span className="text-xs text-muted-foreground">None</span>
              )}
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-foreground">In dependency path of ({data.impacted_services.length})</div>
              <div className="flex flex-wrap gap-1.5">
                {data.impacted_services.map((s) => (
                  <Link key={s.id} href={`/services/${s.id}`} className="rounded-md bg-muted px-2 py-0.5 text-xs hover:bg-muted/70">
                    {s.name}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <SectionCard
          title={
            <span className="flex items-center gap-1.5">
              <ArrowDownRight className="size-4" /> Depends on
            </span>
          }
          bodyClassName="p-0"
        >
          <DepList items={data.depends_on} empty="No recorded dependencies" />
        </SectionCard>
        <SectionCard
          title={
            <span className="flex items-center gap-1.5">
              <ArrowUpRight className="size-4" /> Relied on by
            </span>
          }
          bodyClassName="p-0"
        >
          <DepList items={data.dependents} empty="No assets depend on this asset" />
        </SectionCard>
      </div>

      <SectionCard title="Control coverage" description="Controls in scope for this asset and their latest assessment" className="mt-4" bodyClassName="p-0">
        {data.controls.length === 0 ? (
          <EmptyState title="No controls scoped to this asset" />
        ) : (
          <ul className="divide-y">
            {data.controls.map((c) => (
              <li key={c.control_id} className="flex flex-wrap items-start gap-3 px-4 py-2.5">
                <StatusBadge status={c.status} className="mt-0.5" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm">
                    <RefLink href={`/controls/${c.control_id}`}>{c.control_id}</RefLink> {c.control_name}
                  </div>
                  {c.latest_assessment && <p className="mt-0.5 text-xs text-muted-foreground">{c.latest_assessment.explanation}</p>}
                </div>
                {c.latest_assessment && (
                  <div className="text-right text-xs">
                    <RefLink href={`/assessments/${c.latest_assessment.id}`}>{c.latest_assessment.ref}</RefLink>
                    <div className="text-muted-foreground">{relativeTime(c.latest_assessment.assessed_at)}</div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title="Findings" className="mt-4" bodyClassName="p-0">
        {data.findings.length === 0 ? (
          <EmptyState title="No findings recorded for this asset" />
        ) : (
          <ul className="divide-y">
            {data.findings.map((f) => (
              <li key={f.id} className="flex cursor-pointer items-center gap-3 px-4 py-2.5 hover:bg-muted/40" onClick={() => router.push(`/findings/${f.id}`)}>
                <ScorePill score={f.risk_score} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{f.title}</div>
                  <div className="text-xs text-muted-foreground">
                    <span className="mono">{f.ref}</span> · detected {formatDate(f.detected_at)}
                  </div>
                </div>
                <SeverityBadge severity={f.severity} />
                <FindingStatusBadge status={f.status} />
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title="Assessment history" description="Most recent 60 immutable assessments across all controls" className="mt-4" bodyClassName="p-0">
        <ul className="max-h-96 divide-y overflow-auto">
          {data.assessment_history.map((h) => (
            <li key={h.id} className="flex items-center gap-3 px-4 py-2 text-xs">
              <StatusBadge status={h.result} />
              <RefLink href={`/assessments/${h.id}`}>{h.ref}</RefLink>
              <span className="mono text-muted-foreground">{h.control_id}</span>
              <span className="min-w-0 flex-1 truncate">{h.explanation}</span>
              <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(h.assessed_at)}</span>
            </li>
          ))}
        </ul>
      </SectionCard>

      {editing && (
        <AssetFormDialog open onOpenChange={setEditing} asset={a} serviceIds={data.direct_services.map((s) => s.id)} />
      )}
    </div>
  );
}
