"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, Globe, Network } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  Field,
  FindingStatusBadge,
  KpiCard,
  LoadingBlock,
  PageHeader,
  RefLink,
  ScorePill,
  SectionCard,
  SeverityBadge,
  StatusBadge,
} from "@/components/common";
import { DependencyMap, type GraphEdge, type GraphNode } from "@/components/dependency-map";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Exposure, Finding } from "@/lib/types";

type ServiceDetail = {
  service: {
    id: string;
    name: string;
    description: string;
    tier: string;
    business_owner: string;
    customer_facing: boolean;
    rto_hours: number;
    daily_transaction_volume: string;
  };
  exposure: Exposure;
  assets: {
    id: string;
    name: string;
    asset_type: string;
    criticality: string;
    direct: boolean;
    control_status: string;
    has_redundancy: boolean;
    internet_exposed: boolean;
  }[];
  findings: Finding[];
  single_points_of_failure: { asset_id: string; name: string; asset_type: string; criticality: string; shared_by_services: number }[];
};

export default function ServiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["service", id],
    queryFn: () => api<ServiceDetail>(`/business-services/${id}`),
  });
  const graph = useQuery({
    queryKey: ["graph", id, false],
    queryFn: () => api<{ nodes: GraphNode[]; edges: GraphEdge[] }>("/business-services/graph", { params: { service_id: id } }),
  });

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !data) return <LoadingBlock rows={10} />;
  const s = data.service;
  const failing = data.assets.filter((a) => a.control_status === "Ineffective").length;

  return (
    <div>
      <Link href="/services" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-3.5" /> Business Services
      </Link>
      <PageHeader
        eyebrow={`${s.id} · ${s.tier}${s.customer_facing ? " · customer-facing" : ""}`}
        title={s.name}
        description={s.description}
        actions={
          <Link href={`/services?service=${s.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
            <Network className="size-3.5" /> Open in map
          </Link>
        }
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard label="Potential exposure index" value={data.exposure.index} sub={`${data.exposure.level} · ${data.exposure.formula}`} tone={data.exposure.index >= 60 ? "danger" : data.exposure.index >= 40 ? "warning" : "success"} />
        <KpiCard label="Unresolved findings in path" value={data.findings.length} tone={data.findings.length ? "warning" : "success"} />
        <KpiCard label="Assets in dependency path" value={data.assets.length} sub={`${failing} with an ineffective control`} tone={failing ? "danger" : "default"} />
        <KpiCard label="Single points of failure" value={data.single_points_of_failure.length} tone={data.single_points_of_failure.length ? "danger" : "success"} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <SectionCard title="Service profile">
          <dl className="grid grid-cols-1 gap-3">
            <Field label="Business owner">{s.business_owner}</Field>
            <Field label="Recovery time objective">{s.rto_hours} hours</Field>
            <Field label="Volume">{s.daily_transaction_volume}</Field>
          </dl>
        </SectionCard>
        <SectionCard title="Unresolved findings in the dependency path" className="xl:col-span-2" bodyClassName="p-0">
          {data.findings.length === 0 ? (
            <EmptyState title="No unresolved findings affect this service's dependency path" />
          ) : (
            <ul className="divide-y">
              {data.findings.map((f) => (
                <li key={f.id} className="flex cursor-pointer items-center gap-3 px-4 py-2.5 hover:bg-muted/40" onClick={() => router.push(`/findings/${f.id}`)}>
                  <ScorePill score={f.risk_score} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{f.title}</div>
                    <div className="text-xs text-muted-foreground">
                      <span className="mono">{f.ref}</span> · {f.asset_id} · due {formatDate(f.due_date)}
                    </div>
                  </div>
                  <SeverityBadge severity={f.severity} />
                  <FindingStatusBadge status={f.status} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Dependency map" className="mt-4" bodyClassName="p-0">
        <div className="h-[520px]">
          {graph.data ? (
            <DependencyMap
              nodes={graph.data.nodes}
              edges={graph.data.edges}
              highlight={null}
              onNodeClick={(n) => router.push(n.kind === "asset" ? `/services?service=${id}&asset=${n.id}` : `/services/${n.id}`)}
            />
          ) : (
            <LoadingBlock rows={8} className="p-4" />
          )}
        </div>
      </SectionCard>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <SectionCard title="Assets in dependency path" className="xl:col-span-2" bodyClassName="p-0">
          <ul className="max-h-[420px] divide-y overflow-auto">
            {data.assets.map((a) => (
              <li key={a.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <RefLink href={`/assets/${a.id}`}>{a.id}</RefLink> <span>{a.name}</span>
                  <div className="text-xs text-muted-foreground">
                    {a.asset_type} · {a.direct ? "direct dependency" : "transitive dependency"}
                  </div>
                </div>
                {a.internet_exposed && <Globe className="size-3.5 text-orange-600" />}
                <SeverityBadge severity={a.criticality} />
                <StatusBadge status={a.control_status} />
              </li>
            ))}
          </ul>
        </SectionCard>
        <SectionCard title="Single points of failure" description="High/critical assets without redundancy" bodyClassName="p-0">
          {data.single_points_of_failure.length === 0 ? (
            <EmptyState title="None identified" />
          ) : (
            <ul className="divide-y">
              {data.single_points_of_failure.map((p) => (
                <li key={p.asset_id} className="px-4 py-2 text-sm">
                  <div className="flex items-center gap-1.5">
                    <AlertTriangle className="size-3.5 text-red-600" />
                    <RefLink href={`/services?service=${id}&asset=${p.asset_id}`}>{p.asset_id}</RefLink>
                  </div>
                  <div>{p.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {p.asset_type} · {p.criticality} · shared by {p.shared_by_services} services
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
