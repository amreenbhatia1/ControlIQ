"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Info, X } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import {
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  RefLink,
  ScorePill,
  SectionCard,
  SeverityBadge,
  StatusBadge,
} from "@/components/common";
import { DependencyMap, type GraphEdge, type GraphNode, type Highlight } from "@/components/dependency-map";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { STATUS_COLORS, scoreColor } from "@/lib/format";
import type { Exposure, Finding, ServiceRef } from "@/lib/types";
import { cn } from "@/lib/utils";

type ServiceSummary = {
  id: string;
  name: string;
  description: string;
  tier: string;
  business_owner: string;
  customer_facing: boolean;
  rto_hours: number;
  daily_transaction_volume: string;
  asset_count: number;
  direct_asset_count: number;
  unresolved_findings: number;
  critical_findings: number;
  exposure: Exposure;
  spof_count: number;
};

type Focus = {
  asset_id: string;
  asset_name: string;
  upstream: string[];
  downstream: string[];
  impacted_services: ServiceRef[];
  paths: string[][];
  related_findings: Finding[];
  asset_exposure: Exposure;
  is_spof: boolean;
  shared_by_services: number;
};

type GraphResponse = { nodes: GraphNode[]; edges: GraphEdge[]; focus: Focus | null };

function buildHighlight(focus: Focus, edges: GraphEdge[]): Highlight {
  const a = focus.asset_id;
  const up = new Set(focus.upstream);
  const down = new Set(focus.downstream);
  const svc = new Set(focus.impacted_services.map((s) => s.id));
  const nodes = new Set<string>([a, ...up, ...down, ...svc]);
  const pathEdges = new Set<string>();
  for (const e of edges) {
    const upward = (up.has(e.source) || svc.has(e.source) || e.source === a) && (up.has(e.target) || e.target === a);
    const downward = (e.source === a || down.has(e.source)) && down.has(e.target);
    if (upward || downward) pathEdges.add(e.id);
  }
  return { focus: a, nodes, pathEdges };
}

function ServiceCards({ services, selected, onSelect }: { services: ServiceSummary[]; selected: string; onSelect: (id: string) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
      {services.map((s) => (
        <button
          key={s.id}
          onClick={() => onSelect(selected === s.id ? "" : s.id)}
          className={cn(
            "rounded-xl border bg-card p-3 text-left transition-shadow hover:shadow-md",
            selected === s.id && "ring-2 ring-primary",
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{s.name}</div>
              <div className="text-[11px] text-muted-foreground">
                {s.tier} · RTO {s.rto_hours}h · {s.asset_count} assets in path
              </div>
            </div>
            <span
              className="rounded-md px-1.5 py-0.5 text-xs font-semibold text-white tabular-nums"
              style={{ backgroundColor: s.exposure.index ? scoreColor(s.exposure.index) : "#94a3b8" }}
              title={s.exposure.formula}
            >
              {s.exposure.index}
            </span>
          </div>
          <div className="mt-2 h-1.5 rounded-full bg-muted">
            <div className="h-1.5 rounded-full" style={{ width: `${s.exposure.index}%`, backgroundColor: scoreColor(s.exposure.index) }} />
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
            <span className={cn(s.unresolved_findings && "font-medium text-foreground")}>{s.unresolved_findings} unresolved</span>
            {s.critical_findings > 0 && <span className="font-medium text-red-600">{s.critical_findings} critical</span>}
            <span className={cn(s.spof_count && "text-red-700")}>{s.spof_count} SPOF</span>
            <span>{s.exposure.level} potential exposure</span>
          </div>
        </button>
      ))}
    </div>
  );
}

function FocusPanel({ focus, nodes, onClose }: { focus: Focus; nodes: Map<string, GraphNode>; onClose: () => void }) {
  const name = (id: string) => nodes.get(id)?.label ?? id;
  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <RefLink href={`/assets/${focus.asset_id}`}>{focus.asset_id}</RefLink>
          <div className="font-semibold">{focus.asset_name}</div>
        </div>
        <button onClick={onClose} className="rounded p-1 hover:bg-muted" aria-label="Clear focus">
          <X className="size-4" />
        </button>
      </div>
      {focus.is_spof && (
        <div className="rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-800">
          <div className="flex items-center gap-1 font-semibold">
            <AlertTriangle className="size-3.5" /> Potential single point of failure
          </div>
          High or critical asset with no recorded redundancy, in the dependency path of {focus.shared_by_services} business service
          {focus.shared_by_services === 1 ? "" : "s"}.
        </div>
      )}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-md border p-2">
          <div className="text-lg font-semibold">{focus.upstream.length}</div>
          <div className="text-[10px] text-muted-foreground">assets rely on it</div>
        </div>
        <div className="rounded-md border p-2">
          <div className="text-lg font-semibold">{focus.downstream.length}</div>
          <div className="text-[10px] text-muted-foreground">assets it relies on</div>
        </div>
        <div className="rounded-md border p-2">
          <div className="text-lg font-semibold" style={{ color: focus.asset_exposure.index ? scoreColor(focus.asset_exposure.index) : undefined }}>
            {focus.asset_exposure.index}
          </div>
          <div className="text-[10px] text-muted-foreground">asset exposure</div>
        </div>
      </div>
      <div>
        <div className="mb-1 text-xs font-semibold">Potential exposure — business services ({focus.impacted_services.length})</div>
        <p className="mb-1.5 text-[11px] text-muted-foreground">
          Services whose dependency path includes this asset. A control failure here could potentially affect them; this is not a
          confirmed impact.
        </p>
        <ul className="space-y-1">
          {focus.impacted_services.map((s) => (
            <li key={s.id} className="flex items-center justify-between text-xs">
              <Link href={`/services/${s.id}`} className="hover:underline">
                {s.name}
              </Link>
              <span className="text-muted-foreground">{s.tier}</span>
            </li>
          ))}
        </ul>
      </div>
      {focus.paths.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold">Dependency paths</div>
          <ul className="max-h-40 space-y-1.5 overflow-auto">
            {focus.paths.map((p) => (
              <li key={p.join(">")} className="flex flex-wrap items-center gap-1 text-[11px]">
                {p.map((id, i) => (
                  <span key={id} className="flex items-center gap-1">
                    {i > 0 && <ArrowRight className="size-3 text-muted-foreground" />}
                    <span className={cn("rounded px-1", i === 0 ? "bg-primary text-primary-foreground" : "bg-muted")}>{name(id)}</span>
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <div className="mb-1 text-xs font-semibold">Unresolved findings on this asset and its dependencies</div>
        {focus.related_findings.length === 0 ? (
          <p className="text-xs text-muted-foreground">None</p>
        ) : (
          <ul className="space-y-1.5">
            {focus.related_findings.map((f) => (
              <li key={f.id}>
                <Link href={`/findings/${f.id}`} className="flex items-start gap-2 text-xs hover:underline">
                  <ScorePill score={f.risk_score} />
                  <span>
                    <span className="mono">{f.ref}</span> {f.title}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="space-y-2 text-xs">
      <p className="text-muted-foreground">
        Click an asset to trace which business services depend on it and which assets it relies on. Click a service to filter
        the map.
      </p>
      <div className="font-semibold">Control status (left border)</div>
      <div className="grid grid-cols-2 gap-1">
        {Object.entries(STATUS_COLORS).map(([k, c]) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ backgroundColor: c }} /> {k}
          </span>
        ))}
      </div>
      <div className="font-semibold">Markers</div>
      <ul className="space-y-1 text-muted-foreground">
        <li>
          <span className="rounded bg-red-600 px-1 text-[9px] font-semibold text-white">SPOF</span> High/critical asset without redundancy
        </li>
        <li>Numbered badge — unresolved findings (coloured by highest score)</li>
        <li>Dashed edge — “hosted on” relationship</li>
      </ul>
    </div>
  );
}

function ServicesInner() {
  const router = useRouter();
  const params = useSearchParams();
  const serviceId = params.get("service") ?? "";
  const assetId = params.get("asset") ?? "";
  const hosts = params.get("hosts") === "1";

  const setParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    router.replace(`/services${next.toString() ? `?${next}` : ""}`, { scroll: false });
  };

  const services = useQuery({ queryKey: ["services"], queryFn: () => api<ServiceSummary[]>("/business-services") });
  const graph = useQuery({
    queryKey: ["graph", serviceId, hosts],
    queryFn: () => api<GraphResponse>("/business-services/graph", { params: { service_id: serviceId, include_hosts: hosts || undefined } }),
  });
  const focus = useQuery({
    queryKey: ["graph-focus", assetId],
    queryFn: () => api<GraphResponse>("/business-services/graph", { params: { asset_id: assetId } }),
    enabled: Boolean(assetId),
  });

  const nodes = useMemo(() => graph.data?.nodes ?? [], [graph.data]);
  const edges = useMemo(() => graph.data?.edges ?? [], [graph.data]);
  const nodeMap = useMemo(() => {
    const m = new Map<string, GraphNode>();
    nodes.forEach((n) => m.set(n.id, n));
    focus.data?.nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [nodes, focus.data]);
  const highlight = useMemo(
    () => (assetId && focus.data?.focus ? buildHighlight(focus.data.focus, edges) : null),
    [assetId, focus.data, edges],
  );
  const focusHidden = Boolean(assetId && nodes.length && !nodes.some((n) => n.id === assetId));
  const spofs = nodes.filter((n) => n.kind === "asset" && n.spof);

  return (
    <div>
      <PageHeader
        title="Business Services"
        description="How technology assets support Alpha Beta Bank's business services. Exposure figures describe potential exposure derived from unresolved findings in each service's dependency path — not confirmed incidents."
      />
      {services.error ? (
        <ErrorState error={services.error} />
      ) : services.isLoading ? (
        <LoadingBlock rows={4} />
      ) : (
        <ServiceCards services={services.data ?? []} selected={serviceId} onSelect={(id) => setParams({ service: id, asset: null })} />
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_340px]">
        <SectionCard
          title="Dependency map"
          description={serviceId ? `Dependency closure of ${nodeMap.get(serviceId)?.label ?? serviceId}` : "All business services"}
          bodyClassName="p-0"
          actions={
            <div className="flex flex-wrap items-center gap-3">
              <SimpleSelect
                value={serviceId}
                onChange={(v) => setParams({ service: v })}
                options={(services.data ?? []).map((s) => ({ value: s.id, label: s.name }))}
                allLabel="All services"
                className="min-w-44"
              />
              <label className="flex items-center gap-1.5 text-xs">
                <Switch checked={hosts} onCheckedChange={(v) => setParams({ hosts: v ? "1" : null })} /> Hosting layer
              </label>
            </div>
          }
        >
          <div className="relative h-[640px] w-full">
            {graph.error ? (
              <div className="p-4">
                <ErrorState error={graph.error} />
              </div>
            ) : graph.isLoading ? (
              <LoadingBlock rows={10} className="p-4" />
            ) : nodes.length === 0 ? (
              <EmptyState title="No dependencies recorded" />
            ) : (
              <DependencyMap
                nodes={nodes}
                edges={edges}
                highlight={highlight}
                onNodeClick={(n) => (n.kind === "service" ? setParams({ service: n.id, asset: null }) : setParams({ asset: n.id }))}
                onPaneClick={() => assetId && setParams({ asset: null })}
              />
            )}
            {focusHidden && (
              <div className="absolute top-3 left-3 flex items-center gap-2 rounded-md border bg-amber-50 px-3 py-1.5 text-xs text-amber-900 shadow-sm">
                <Info className="size-3.5" /> {assetId} is not in the current view.
                {!hosts && (
                  <button className="font-medium underline" onClick={() => setParams({ hosts: "1" })}>
                    Show hosting layer
                  </button>
                )}
                {serviceId && (
                  <button className="font-medium underline" onClick={() => setParams({ service: null })}>
                    Show all services
                  </button>
                )}
              </div>
            )}
          </div>
        </SectionCard>
        <div className="space-y-4">
          <SectionCard title={assetId ? "Impact trace" : "How to read the map"}>
            {assetId ? (
              focus.isLoading ? (
                <LoadingBlock rows={6} />
              ) : focus.error ? (
                <ErrorState error={focus.error} />
              ) : focus.data?.focus ? (
                <FocusPanel focus={focus.data.focus} nodes={nodeMap} onClose={() => setParams({ asset: null })} />
              ) : null
            ) : (
              <Legend />
            )}
          </SectionCard>
          <SectionCard title={`Single points of failure in view (${spofs.length})`} bodyClassName="p-0">
            {spofs.length === 0 ? (
              <EmptyState title="None identified in this view" />
            ) : (
              <ul className="max-h-72 divide-y overflow-auto">
                {spofs
                  .sort((a, b) => (b.shared_by_services ?? 0) - (a.shared_by_services ?? 0))
                  .map((n) => (
                    <li key={n.id}>
                      <button onClick={() => setParams({ asset: n.id })} className="flex w-full items-center gap-2 px-4 py-2 text-left text-xs hover:bg-muted/40">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{n.label}</span>
                          <span className="mono text-muted-foreground">{n.id}</span>
                        </span>
                        <SeverityBadge severity={n.criticality ?? "Low"} />
                        <span className="text-muted-foreground">×{n.shared_by_services}</span>
                      </button>
                    </li>
                  ))}
              </ul>
            )}
          </SectionCard>
          {assetId && nodeMap.get(assetId)?.control_status && (
            <div className="text-xs text-muted-foreground">
              Current control status of {assetId}: <StatusBadge status={nodeMap.get(assetId)!.control_status!} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ServicesPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <ServicesInner />
    </Suspense>
  );
}
