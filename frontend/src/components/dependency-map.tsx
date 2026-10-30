"use client";

import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { Graph, layout } from "@dagrejs/dagre";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Briefcase, Globe } from "lucide-react";
import { STATUS_COLORS, scoreColor } from "@/lib/format";
import { cn } from "@/lib/utils";

export type GraphNode = {
  id: string;
  kind: "service" | "asset";
  label: string;
  sublabel: string;
  tier?: string;
  open_findings: number;
  exposure_index?: number;
  exposure_level?: string;
  asset_type?: string;
  criticality?: string;
  internet_exposed?: boolean;
  has_redundancy?: boolean;
  control_status?: string;
  max_risk_score?: number;
  spof?: boolean;
  shared_by_services?: number;
};

export type GraphEdge = { id: string; source: string; target: string; kind: string; dependency_type: string };

export type Highlight = {
  focus: string;
  nodes: Set<string>;
  pathEdges: Set<string>;
};

type NodeData = GraphNode & { dimmed: boolean; focused: boolean; onPath: boolean };

const NODE_W = 210;
const NODE_H = 58;

function ServiceNode({ data }: NodeProps<Node<NodeData>>) {
  const exposure = data.exposure_index ?? 0;
  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-[oklch(0.25_0.06_260)] px-3 py-2 text-white shadow-sm transition-opacity",
        data.dimmed && "opacity-25",
        data.onPath ? "border-amber-400" : "border-transparent",
      )}
      style={{ width: NODE_W, height: NODE_H }}
    >
      <Handle type="source" position={Position.Right} className="!bg-slate-400" />
      <div className="flex items-center gap-1.5">
        <Briefcase className="size-3.5 shrink-0 opacity-70" />
        <span className="truncate text-xs font-semibold">{data.label}</span>
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] opacity-90">
        <span>{data.tier}</span>
        {exposure > 0 ? (
          <span className="rounded px-1 font-semibold" style={{ backgroundColor: scoreColor(exposure) }}>
            exposure {exposure}
          </span>
        ) : (
          <span className="opacity-70">no open exposure</span>
        )}
      </div>
    </div>
  );
}

function AssetNode({ data }: NodeProps<Node<NodeData>>) {
  const color = STATUS_COLORS[data.control_status ?? "Not Assessed"];
  return (
    <div
      className={cn(
        "relative rounded-lg border bg-white px-3 py-1.5 shadow-sm transition-opacity",
        data.dimmed && "opacity-20",
        data.focused && "ring-4 ring-blue-400",
        data.onPath && !data.focused && "ring-2 ring-amber-400",
      )}
      style={{ width: NODE_W, height: NODE_H, borderLeft: `5px solid ${color}` }}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-400" />
      <Handle type="source" position={Position.Right} className="!bg-slate-400" />
      <div className="flex items-center gap-1">
        <span className="truncate text-xs font-semibold text-slate-900">{data.label}</span>
        {data.internet_exposed && <Globe className="size-3 shrink-0 text-orange-600" />}
      </div>
      <div className="mono truncate text-[10px] text-slate-500">
        {data.sublabel} · {data.asset_type}
      </div>
      <div className="mt-0.5 flex items-center gap-1 text-[9px]">
        <span className="rounded bg-slate-100 px-1 text-slate-600">{data.criticality}</span>
        {data.spof && <span className="rounded bg-red-600 px-1 font-semibold text-white">SPOF</span>}
        {(data.shared_by_services ?? 0) > 1 && <span className="text-slate-500">shared ×{data.shared_by_services}</span>}
      </div>
      {data.open_findings > 0 && (
        <span
          className="absolute -top-2 -right-2 flex size-5 items-center justify-center rounded-full text-[10px] font-bold text-white shadow"
          style={{ backgroundColor: scoreColor(data.max_risk_score ?? 0) }}
          title={`${data.open_findings} unresolved finding(s), max score ${data.max_risk_score}`}
        >
          {data.open_findings}
        </span>
      )}
    </div>
  );
}

const nodeTypes = { service: ServiceNode, asset: AssetNode };

function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]) {
  const g = new Graph();
  g.setGraph({ rankdir: "LR", nodesep: 18, ranksep: 70, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  layout(g);
  const pos: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n) => {
    const p = g.node(n.id);
    pos[n.id] = { x: (p?.x ?? 0) - NODE_W / 2, y: (p?.y ?? 0) - NODE_H / 2 };
  });
  return pos;
}

export function DependencyMap({
  nodes,
  edges,
  highlight,
  onNodeClick,
  onPaneClick,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlight: Highlight | null;
  onNodeClick: (n: GraphNode) => void;
  onPaneClick?: () => void;
}) {
  const positions = useMemo(() => layoutGraph(nodes, edges), [nodes, edges]);

  const rfNodes: Node<NodeData>[] = useMemo(
    () =>
      nodes.map((n) => ({
        id: n.id,
        type: n.kind,
        position: positions[n.id],
        data: {
          ...n,
          dimmed: Boolean(highlight && !highlight.nodes.has(n.id)),
          focused: highlight?.focus === n.id,
          onPath: Boolean(highlight && highlight.nodes.has(n.id)),
        },
        draggable: false,
      })),
    [nodes, positions, highlight],
  );

  const rfEdges: Edge[] = useMemo(
    () =>
      edges.map((e) => {
        const onPath = highlight?.pathEdges.has(e.id) ?? false;
        const dimmed = Boolean(highlight && !onPath);
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          animated: onPath,
          label: onPath && e.dependency_type !== "depends on" ? e.dependency_type : undefined,
          labelStyle: { fontSize: 10 },
          style: {
            stroke: onPath ? "#d97706" : e.kind === "service" ? "#1e3a8a" : "#94a3b8",
            strokeWidth: onPath ? 2.5 : 1.2,
            opacity: dimmed ? 0.12 : 1,
            strokeDasharray: e.dependency_type === "hosted on" ? "4 3" : undefined,
          },
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: onPath ? "#d97706" : "#94a3b8" },
        };
      }),
    [edges, highlight],
  );

  return (
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.1 }}
      minZoom={0.1}
      maxZoom={1.6}
      nodesConnectable={false}
      onNodeClick={(_, n) => onNodeClick(n.data as GraphNode)}
      onPaneClick={onPaneClick}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={20} color="#e2e8f0" />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        nodeColor={(n) => ((n.data as GraphNode).kind === "service" ? "#1e3a8a" : STATUS_COLORS[(n.data as GraphNode).control_status ?? "Not Assessed"])}
      />
    </ReactFlow>
  );
}
