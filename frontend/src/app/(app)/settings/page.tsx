"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination, SectionCard, Spinner } from "@/components/common";
import { DemoPanel } from "@/components/demo-panel";
import { api } from "@/lib/api";
import { formatDateTime, relativeTime } from "@/lib/format";
import { useCan, useUsers } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import { normaliseWeights, weightsSumToOne } from "@/lib/scoring";
import type { Page } from "@/lib/types";
import { cn } from "@/lib/utils";

type SettingsResponse = {
  risk_scoring: {
    bands: Record<string, number>;
    weights: Record<string, number>;
    methodology_version: string;
    factor_labels: Record<string, string>;
    defaults: Record<string, number>;
  };
  validation_workflow: { mode: string };
  remediation_sla_days: Record<string, number>;
};

type Role = { key: string; name: string; description: string; permissions: string[] };

type AuditEntry = {
  id: number;
  occurred_at: string;
  actor: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  outcome: string;
  ip_address: string | null;
  details: Record<string, unknown>;
};

const TABS = [
  { value: "demo", label: "Demo scenarios" },
  { value: "scoring", label: "Risk scoring" },
  { value: "workflow", label: "Validation workflow" },
  { value: "access", label: "Users & roles" },
  { value: "audit", label: "Audit log" },
];

function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: () => api<SettingsResponse>("/settings") });
}

function sliderValue(v: number | readonly number[]): number {
  return Array.isArray(v) ? (v[0] as number) : (v as number);
}

function ScoringTab() {
  const can = useCan();
  const qc = useQueryClient();
  const { data, isLoading, error } = useSettings();
  const [draft, setDraft] = useState<Record<string, number> | null>(null);
  const save = useMutation({
    mutationFn: (weights: Record<string, number>) => api<{ message: string }>("/settings/risk-scoring", { method: "PUT", body: { weights } }),
    onSuccess: (r) => {
      toast.success(r.message);
      setDraft(null);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: Error) => toast.error("Weights rejected", { description: e.message }),
  });
  if (error) return <ErrorState error={error} />;
  if (isLoading || !data) return <LoadingBlock rows={6} />;
  const rs = data.risk_scoring;
  const editable = can(PERM.SETTINGS_WRITE);
  const weights = draft ?? rs.weights;
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const balanced = weightsSumToOne(weights);
  const round = (w: Record<string, number>) => Object.fromEntries(Object.entries(w).map(([k, v]) => [k, Math.round(v * 1000) / 1000]));

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <SectionCard
        title="Factor weights"
        description={`Methodology v${rs.methodology_version}. Score = Σ (factor value × weight) × 100. New weights apply to findings from the next assessment run.`}
        actions={!editable && <span className="flex items-center gap-1 text-xs text-muted-foreground"><Lock className="size-3" /> Administrator only</span>}
      >
        <ul className="space-y-5">
          {Object.keys(rs.defaults).map((k) => (
            <li key={k}>
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="font-medium">{rs.factor_labels[k] ?? k}</span>
                <span className="tabular-nums">
                  {(weights[k] * 100).toFixed(1)}%
                  <span className="ml-2 text-xs text-muted-foreground">default {(rs.defaults[k] * 100).toFixed(0)}%</span>
                </span>
              </div>
              <Slider
                value={[weights[k]]}
                min={0}
                max={0.6}
                step={0.01}
                disabled={!editable}
                onValueChange={(v) => setDraft({ ...weights, [k]: sliderValue(v) })}
                aria-label={rs.factor_labels[k] ?? k}
              />
            </li>
          ))}
        </ul>
        <div className={cn("mt-5 rounded-md border px-3 py-2 text-sm", balanced ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-900")}>
          Total weight: <span className="font-semibold tabular-nums">{(total * 100).toFixed(1)}%</span>
          {balanced ? " — valid" : " — weights must sum to 100% before saving"}
        </div>
        {editable && (
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="outline" disabled={balanced} onClick={() => setDraft(round(normaliseWeights(weights)))}>
              Normalise to 100%
            </Button>
            <Button size="sm" variant="outline" onClick={() => setDraft({ ...rs.defaults })}>
              Restore defaults
            </Button>
            {draft && (
              <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
                Discard changes
              </Button>
            )}
            <Button size="sm" disabled={!draft || !balanced || save.isPending} onClick={() => save.mutate(round(weights))}>
              {save.isPending && <Spinner className="size-3.5" />} Save weights
            </Button>
          </div>
        )}
      </SectionCard>
      <div className="space-y-4">
        <SectionCard title="Severity bands">
          <ul className="space-y-1.5 text-sm">
            {Object.entries(rs.bands)
              .sort((a, b) => b[1] - a[1])
              .map(([sev, min]) => (
                <li key={sev} className="flex justify-between">
                  <span>{sev}</span>
                  <span className="tabular-nums text-muted-foreground">score ≥ {min}</span>
                </li>
              ))}
            <li className="flex justify-between">
              <span>Low</span>
              <span className="tabular-nums text-muted-foreground">below {rs.bands.Medium}</span>
            </li>
          </ul>
        </SectionCard>
        <SectionCard title="Remediation SLA">
          <ul className="space-y-1.5 text-sm">
            {Object.entries(data.remediation_sla_days)
              .sort((a, b) => a[1] - b[1])
              .map(([sev, days]) => (
                <li key={sev} className="flex justify-between">
                  <span>{sev}</span>
                  <span className="tabular-nums text-muted-foreground">{days} days</span>
                </li>
              ))}
          </ul>
        </SectionCard>
      </div>
    </div>
  );
}

function WorkflowTab() {
  const can = useCan();
  const qc = useQueryClient();
  const { data, isLoading, error } = useSettings();
  const save = useMutation({
    mutationFn: (mode: string) => api("/settings/validation-workflow", { method: "PUT", body: { mode } }),
    onSuccess: () => {
      toast.success("Validation workflow updated");
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error("Update rejected", { description: e.message }),
  });
  if (error) return <ErrorState error={error} />;
  if (isLoading || !data) return <LoadingBlock rows={4} />;
  const editable = can(PERM.SETTINGS_WRITE);
  const options = [
    {
      value: "auto_resolve",
      title: "Automatic validation",
      body: "A finding is resolved automatically when a reassessment passes against updated evidence. Remediation owners cannot resolve findings themselves.",
    },
    {
      value: "analyst_signoff",
      title: "Analyst sign-off",
      body: "A passing reassessment moves the finding to Pending Validation. A Risk Analyst or Administrator must then sign off; sign-off is refused unless the latest assessment is Effective.",
    },
  ];
  return (
    <SectionCard title="Finding validation" description="In both modes, resolution requires a passing reassessment — manual closure is never permitted.">
      <div className="grid gap-3 md:grid-cols-2">
        {options.map((o) => {
          const active = data.validation_workflow.mode === o.value;
          return (
            <button
              key={o.value}
              disabled={!editable || active || save.isPending}
              onClick={() => save.mutate(o.value)}
              className={cn("rounded-lg border p-4 text-left disabled:cursor-default", active ? "border-primary ring-2 ring-primary" : editable && "hover:bg-muted/40")}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">{o.title}</span>
                {active && <span className="rounded bg-primary px-1.5 text-[10px] font-medium text-primary-foreground">Active</span>}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{o.body}</p>
            </button>
          );
        })}
      </div>
      {!editable && (
        <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
          <Lock className="size-3" /> Only administrators can change the validation workflow.
        </p>
      )}
    </SectionCard>
  );
}

function AccessTab() {
  const users = useUsers();
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles") });
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
      <SectionCard title="Users" description="Synthetic Alpha Beta Bank staff accounts" bodyClassName="p-0">
        {users.isLoading ? (
          <LoadingBlock className="p-4" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-xs">Name</TableHead>
                <TableHead className="text-xs">Role</TableHead>
                <TableHead className="text-xs">Team</TableHead>
                <TableHead className="text-xs">Risk approver</TableHead>
                <TableHead className="text-xs">Last login</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(users.data ?? []).map((u) => (
                <TableRow key={u.id}>
                  <TableCell>
                    <div className="text-sm font-medium">{u.full_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {u.title} · {u.email}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs">{u.role}</TableCell>
                  <TableCell className="text-xs">{u.team}</TableCell>
                  <TableCell className="text-xs">{u.can_approve_risk ? "Yes" : "—"}</TableCell>
                  <TableCell className="text-xs">{relativeTime(u.last_login_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>
      <SectionCard title="Roles" description="Permissions are enforced by the API on every request">
        <ul className="space-y-4">
          {(roles.data ?? []).map((r) => (
            <li key={r.key}>
              <div className="text-sm font-semibold">{r.name}</div>
              <p className="text-xs text-muted-foreground">{r.description}</p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {r.permissions.map((p) => (
                  <span key={p} className="mono rounded bg-muted px-1.5 py-0.5 text-[10px]">
                    {p}
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </SectionCard>
    </div>
  );
}

function AuditTab() {
  const can = useCan();
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const allowed = can(PERM.AUDIT_READ);
  const { data, isLoading, error } = useQuery({
    queryKey: ["audit", page, action],
    queryFn: () => api<Page<AuditEntry>>("/audit-logs", { params: { page, page_size: 50, action } }),
    enabled: allowed,
    placeholderData: keepPreviousData,
  });
  if (!allowed) return <EmptyState title="Audit log access is restricted to administrators" icon={Lock} />;
  return (
    <SectionCard
      title="Audit log"
      description="Security-relevant events: authentication, uploads, workflow changes, configuration, reports and resets"
      bodyClassName="p-0"
      actions={
        <Input
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
          placeholder="Filter by action prefix, e.g. finding."
          className="h-8 w-64 text-sm"
        />
      }
    >
      {error ? (
        <div className="p-4">
          <ErrorState error={error} />
        </div>
      ) : isLoading ? (
        <LoadingBlock className="p-4" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-xs">Time</TableHead>
                <TableHead className="text-xs">Actor</TableHead>
                <TableHead className="text-xs">Action</TableHead>
                <TableHead className="text-xs">Entity</TableHead>
                <TableHead className="text-xs">Outcome</TableHead>
                <TableHead className="text-xs">Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.items ?? []).map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="text-xs whitespace-nowrap">{formatDateTime(a.occurred_at)}</TableCell>
                  <TableCell className="text-xs">{a.actor ?? "system"}</TableCell>
                  <TableCell className="mono text-xs">{a.action}</TableCell>
                  <TableCell className="mono text-xs">{[a.entity_type, a.entity_id].filter(Boolean).join(" ")}</TableCell>
                  <TableCell>
                    <span className={cn("text-xs font-medium", a.outcome === "success" ? "text-emerald-700" : "text-red-700")}>{a.outcome}</span>
                  </TableCell>
                  <TableCell className="mono max-w-md truncate text-[11px] text-muted-foreground" title={JSON.stringify(a.details)}>
                    {Object.keys(a.details ?? {}).length ? JSON.stringify(a.details) : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pagination page={page} pageSize={50} total={data?.total ?? 0} onPage={setPage} />
        </>
      )}
    </SectionCard>
  );
}

function SettingsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") ?? "demo";
  return (
    <div>
      <PageHeader title="Settings" description="Demonstration scenarios, scoring methodology, validation workflow, access and audit." />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/settings?tab=${v}`, { scroll: false })} className="mb-4">
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value} className="px-3">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {tab === "demo" && <DemoPanel />}
      {tab === "scoring" && <ScoringTab />}
      {tab === "workflow" && <WorkflowTab />}
      {tab === "access" && <AccessTab />}
      {tab === "audit" && <AuditTab />}
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={8} />}>
      <SettingsInner />
    </Suspense>
  );
}
