"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ClipboardCheck,
  Info,
  ListPlus,
  MessageSquarePlus,
  ShieldAlert,
  Sparkles,
  UserCog,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  EmptyState,
  ErrorState,
  Field,
  FindingStatusBadge,
  LoadingBlock,
  PageHeader,
  RefLink,
  SectionCard,
  SeverityBadge,
  Spinner,
  StatusBadge,
  ValidationBadge,
} from "@/components/common";
import { IntelAnswerView } from "@/components/intel-answer";
import { ScoreBreakdownView } from "@/components/score-breakdown";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, relativeTime } from "@/lib/format";
import { useCan, useMe, useUsers } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { Assessment, Evidence, Finding, IntelAnswer, ScoreBreakdown, ServiceRef, UserRef } from "@/lib/types";
import { cn } from "@/lib/utils";

type Action = {
  id: number;
  ref: string;
  title: string;
  description: string;
  owner: UserRef;
  status: string;
  due_date: string;
  created_at: string;
  completed_at: string | null;
  overdue: boolean;
};

type Activity = {
  id: number;
  type: string;
  message: string;
  from_status: string | null;
  to_status: string | null;
  actor: UserRef;
  assessment_id: number | null;
  created_at: string;
};

type FindingDetail = {
  finding: Finding;
  business_impact: string;
  remediation_recommendation: string;
  score_breakdown: ScoreBreakdown;
  impacted_services: ServiceRef[];
  control: { id: string; name: string; domain: string; owner: UserRef; risk_addressed: string };
  asset: { id: string; name: string; asset_type: string; criticality: string; internet_exposed: boolean; environment: string };
  risk_acceptance: {
    justification: string;
    approver: UserRef;
    accepted_by: UserRef;
    accepted_at: string;
    expires_at: string;
  } | null;
  first_assessment_id: number | null;
  latest_assessment: Assessment | null;
  validated_by: Assessment | null;
  assessment_timeline: Assessment[];
  evidence: Evidence[];
  actions: Action[];
  activity: Activity[];
  risks: { id: string; title: string; residual_rating: string }[];
  validation_mode: string;
};

// Mirrors backend MANUAL_TRANSITIONS. "Resolved" is never a manual option.
const TRANSITIONS: Record<string, string[]> = {
  Open: ["In Progress"],
  "In Progress": ["Open", "Pending Validation"],
  "Pending Validation": ["In Progress"],
  "Risk Accepted": ["Open"],
  Resolved: [],
};
const MAX_ACCEPT_DAYS: Record<string, number> = { Critical: 90, High: 180, Medium: 365, Low: 365 };
const ACTION_STATUSES = ["Planned", "In Progress", "Completed", "Cancelled"];

const ACTIVITY_DOT: Record<string, string> = {
  detected: "bg-red-500",
  reopened: "bg-red-500",
  validation_failed: "bg-red-500",
  acceptance_expired: "bg-amber-500",
  risk_acceptance: "bg-amber-500",
  validated: "bg-emerald-500",
  reassessment_passed: "bg-emerald-500",
  status_change: "bg-blue-500",
};

function endOfDayUtc(date: string): string {
  return `${date}T23:59:59Z`;
}

function isoDateOffset(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function useFindingMutation<TBody>(id: string, path: string, success: string, onDone?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TBody) => api(`/findings/${id}/${path}`, { method: "POST", body }),
    onSuccess: () => {
      toast.success(success);
      qc.invalidateQueries();
      onDone?.();
    },
    onError: (e: Error) => toast.error("Action rejected", { description: e.message }),
  });
}

function StatusDialog({ id, f, open, onOpenChange }: { id: string; f: Finding; open: boolean; onOpenChange: (o: boolean) => void }) {
  const options = TRANSITIONS[f.status] ?? [];
  const [to, setTo] = useState(options[0] ?? "");
  const [note, setNote] = useState("");
  const m = useFindingMutation<{ status: string; note: string | null }>(id, "status", "Status updated", () => {
    setNote("");
    onOpenChange(false);
  });
  const needsNote = to === "Pending Validation";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Update finding status</DialogTitle>
          <DialogDescription>
            Findings cannot be marked Resolved manually. Request validation once remediation is complete; the control engine
            resolves the finding when a reassessment passes against updated evidence.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>New status</Label>
            <SimpleSelect value={to} onChange={setTo} options={options} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>{needsNote ? "Remediation performed (required)" : "Note (optional)"}</Label>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={4} maxLength={4000} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!to || (needsNote && !note.trim()) || m.isPending} onClick={() => m.mutate({ status: to, note: note.trim() || null })}>
            {m.isPending && <Spinner className="size-3.5" />} Update status
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AcceptRiskDialog({
  id,
  f,
  open,
  onOpenChange,
}: {
  id: string;
  f: Finding;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const users = useUsers();
  const me = useMe();
  const maxDays = MAX_ACCEPT_DAYS[f.severity] ?? 90;
  const [justification, setJustification] = useState("");
  const [approver, setApprover] = useState("");
  const [expires, setExpires] = useState(isoDateOffset(Math.min(30, maxDays)));
  const m = useFindingMutation<{ justification: string; approver_id: number; expires_at: string }>(id, "accept-risk", "Risk acceptance recorded", () =>
    onOpenChange(false),
  );
  const approvers = (users.data ?? []).filter((u) => u.can_approve_risk && u.id !== me.data?.id);
  const tooShort = justification.trim().length < 40;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Record risk acceptance</DialogTitle>
          <DialogDescription>
            Acceptance is time-bound and requires an accountable approver who is not you. {f.severity} findings may be accepted for at most{" "}
            {maxDays} days. The finding reopens automatically when the acceptance expires.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Business justification</Label>
            <Textarea
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              rows={4}
              placeholder="Why is the residual risk acceptable, and what compensating measures are in place?"
            />
            <div className={cn("text-xs", tooShort ? "text-amber-700" : "text-muted-foreground")}>
              {justification.trim().length} / 40 characters minimum
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Accountable approver</Label>
            <SimpleSelect
              value={approver}
              onChange={setApprover}
              options={approvers.map((u) => ({ value: String(u.id), label: `${u.full_name} — ${u.title}` }))}
              placeholder="Select approver"
              className="w-full"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Expiry / review date</Label>
            <Input
              type="date"
              value={expires}
              min={isoDateOffset(1)}
              max={isoDateOffset(maxDays - 1)}
              onChange={(e) => setExpires(e.target.value)}
              className="w-48"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={tooShort || !approver || !expires || m.isPending}
            onClick={() => m.mutate({ justification: justification.trim(), approver_id: Number(approver), expires_at: endOfDayUtc(expires) })}
          >
            {m.isPending && <Spinner className="size-3.5" />} Record acceptance
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AssignDialog({ id, f, open, onOpenChange }: { id: string; f: Finding; open: boolean; onOpenChange: (o: boolean) => void }) {
  const users = useUsers();
  const [owner, setOwner] = useState(f.assigned_owner ? String(f.assigned_owner.id) : "");
  const m = useFindingMutation<{ owner_id: number }>(id, "assign", "Owner updated", () => onOpenChange(false));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Assign remediation owner</DialogTitle>
        </DialogHeader>
        <SimpleSelect
          value={owner}
          onChange={setOwner}
          options={(users.data ?? []).map((u) => ({ value: String(u.id), label: `${u.full_name} — ${u.title}` }))}
          placeholder="Select owner"
          className="w-full"
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!owner || m.isPending} onClick={() => m.mutate({ owner_id: Number(owner) })}>
            {m.isPending && <Spinner className="size-3.5" />} Assign
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ActionDialog({ id, open, onOpenChange }: { id: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const users = useUsers();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState(isoDateOffset(14));
  const m = useFindingMutation<{ title: string; description: string; owner_id: number | null; due_date: string }>(
    id,
    "actions",
    "Remediation action created",
    () => {
      setTitle("");
      setDescription("");
      onOpenChange(false);
    },
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add remediation action</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} />
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Owner</Label>
              <SimpleSelect
                value={owner}
                onChange={setOwner}
                options={(users.data ?? []).map((u) => ({ value: String(u.id), label: u.full_name }))}
                placeholder="Unassigned"
                className="w-full"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Due date</Label>
              <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={title.trim().length < 3 || !due || m.isPending}
            onClick={() =>
              m.mutate({ title: title.trim(), description: description.trim(), owner_id: owner ? Number(owner) : null, due_date: endOfDayUtc(due) })
            }
          >
            {m.isPending && <Spinner className="size-3.5" />} Create action
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NoteBox({ id }: { id: string }) {
  const [note, setNote] = useState("");
  const m = useFindingMutation<{ note: string }>(id, "notes", "Note added", () => setNote(""));
  return (
    <div className="flex gap-2">
      <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Add a note to the activity history…" className="text-sm" />
      <Button size="sm" variant="outline" className="self-end" disabled={!note.trim() || m.isPending} onClick={() => m.mutate({ note: note.trim() })}>
        <MessageSquarePlus className="size-3.5" /> Add
      </Button>
    </div>
  );
}

function ActionRow({ a, canEdit }: { a: Action; canEdit: boolean }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (status: string) => api(`/remediation/actions/${a.id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => {
      toast.success(`${a.ref} updated`);
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error("Update rejected", { description: e.message }),
  });
  return (
    <li className="px-4 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium">{a.title}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            <span className="mono">{a.ref}</span> · {a.owner?.full_name ?? "Unassigned"} ·{" "}
            <span className={cn(a.overdue && "font-semibold text-red-600")}>
              {a.overdue ? "overdue, " : ""}due {formatDate(a.due_date)}
            </span>
          </div>
          {a.description && <p className="mt-1 text-xs">{a.description}</p>}
        </div>
        {canEdit ? (
          <SimpleSelect value={a.status} onChange={(v) => v !== a.status && m.mutate(v)} options={ACTION_STATUSES} className="h-7 min-w-32 text-xs" disabled={m.isPending} />
        ) : (
          <span className="text-xs whitespace-nowrap">{a.status}</span>
        )}
      </div>
    </li>
  );
}

function AssistantPanel({ findingId }: { findingId: number }) {
  const m = useMutation({
    mutationFn: () =>
      api<IntelAnswer>("/intelligence/ask", { method: "POST", body: { question: "Explain why this finding matters.", finding_id: findingId } }),
  });
  return (
    <SectionCard
      title={
        <span className="flex items-center gap-1.5">
          <Sparkles className="size-4 text-violet-500" /> Risk intelligence
        </span>
      }
      description="Explanation grounded in this finding's stored records"
      actions={
        <Button size="sm" variant="outline" onClick={() => m.mutate()} disabled={m.isPending}>
          {m.isPending && <Spinner className="size-3.5" />} {m.data ? "Regenerate" : "Explain"}
        </Button>
      }
    >
      {m.error ? (
        <ErrorState error={m.error} />
      ) : m.data ? (
        <IntelAnswerView answer={m.data} compact />
      ) : (
        <p className="text-xs text-muted-foreground">Generate an explanation of why this finding matters and what to do next.</p>
      )}
    </SectionCard>
  );
}

export default function FindingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const can = useCan();
  const me = useMe();
  const [dialog, setDialog] = useState<null | "status" | "accept" | "assign" | "action">(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["finding", id],
    queryFn: () => api<FindingDetail>(`/findings/${id}`),
  });
  const confirm = useFindingMutation<undefined>(id, "confirm-validation", "Validation signed off — finding resolved");

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !data) return <LoadingBlock rows={12} />;
  const f = data.finding;
  const myId = me.data?.id;
  const canEdit =
    can(PERM.FINDINGS_UPDATE_ANY) ||
    (can(PERM.FINDINGS_UPDATE) && (f.assigned_owner?.id === myId || data.control.owner?.id === myId));
  const resolved = f.status === "Resolved";
  const canAccept = can(PERM.ACCEPT_RISK) && (f.status === "Open" || f.status === "In Progress");
  const canConfirm = can(PERM.FINDINGS_UPDATE_ANY) && f.status === "Pending Validation";
  const latestPassed = data.latest_assessment?.result === "Effective";

  return (
    <div>
      <Link href="/findings" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-3.5" /> Findings
      </Link>
      <PageHeader
        eyebrow={`${f.ref} · ${f.control_domain}`}
        title={f.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={f.severity} />
            <FindingStatusBadge status={f.status} />
            <span>
              Detected {formatDate(f.detected_at)} · {f.age_days} days old · due {formatDate(f.due_date)}
            </span>
            {f.overdue && <span className="font-semibold text-red-600">Overdue</span>}
          </span>
        }
        actions={
          canEdit &&
          !resolved && (
            <>
              {(TRANSITIONS[f.status] ?? []).length > 0 && (f.status !== "Risk Accepted" || can(PERM.ACCEPT_RISK)) && (
                <Button size="sm" onClick={() => setDialog("status")}>
                  Update status
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => setDialog("assign")}>
                <UserCog className="size-3.5" /> Assign
              </Button>
              <Button size="sm" variant="outline" onClick={() => setDialog("action")}>
                <ListPlus className="size-3.5" /> Action
              </Button>
              {canAccept && (
                <Button size="sm" variant="outline" onClick={() => setDialog("accept")}>
                  <ShieldAlert className="size-3.5" /> Accept risk
                </Button>
              )}
            </>
          )
        }
      />

      {f.status === "Pending Validation" && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-900">
          <ClipboardCheck className="size-4 shrink-0" />
          <div className="flex-1">
            Remediation reported complete. Validation mode: <strong>{data.validation_mode === "auto_resolve" ? "automatic" : "analyst sign-off"}</strong>.{" "}
            {data.validation_mode === "auto_resolve"
              ? "The next assessment that passes against updated evidence resolves this finding."
              : latestPassed
                ? "A passing reassessment exists — an analyst may sign off."
                : "Upload updated evidence and rerun the assessment; sign-off requires a passing reassessment."}
          </div>
          {canConfirm && data.validation_mode !== "auto_resolve" && (
            <Button size="sm" onClick={() => confirm.mutate(undefined)} disabled={confirm.isPending}>
              {confirm.isPending && <Spinner className="size-3.5" />} Sign off validation
            </Button>
          )}
        </div>
      )}
      {resolved && data.validated_by && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <CheckCircle2 className="size-4" />
          Resolved {formatDateTime(f.resolved_at)} — validated by passing assessment{" "}
          <RefLink href={`/assessments/${data.validated_by.id}`}>{data.validated_by.ref}</RefLink>.
        </div>
      )}
      {data.risk_acceptance && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4" /> Risk accepted until {formatDate(data.risk_acceptance.expires_at)} (
            {relativeTime(data.risk_acceptance.expires_at)})
          </div>
          <p className="mt-1">{data.risk_acceptance.justification}</p>
          <div className="mt-1 text-xs">
            Approver: {data.risk_acceptance.approver?.full_name} · recorded by {data.risk_acceptance.accepted_by?.full_name} on{" "}
            {formatDate(data.risk_acceptance.accepted_at)}
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <SectionCard title="What was found">
            <p className="text-sm">{f.description}</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-orange-200 bg-orange-50/60 p-3">
                <div className="mb-1 text-xs font-semibold text-orange-800">Business impact</div>
                <p className="text-sm text-orange-950">{data.business_impact}</p>
              </div>
              <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3">
                <div className="mb-1 text-xs font-semibold text-blue-800">Recommended remediation</div>
                <p className="text-sm text-blue-950">{data.remediation_recommendation}</p>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Risk score breakdown" description="Deterministic, explainable prioritisation — every factor shows its inputs">
            <ScoreBreakdownView breakdown={data.score_breakdown} />
          </SectionCard>

          <SectionCard title="Assessment timeline" description="Immutable assessments of this control scope since detection" bodyClassName="p-0">
            <ol className="max-h-96 divide-y overflow-auto">
              {data.assessment_timeline.map((a) => (
                <li key={a.id} className="flex items-start gap-3 px-4 py-2.5">
                  <StatusBadge status={a.result} className="mt-0.5 shrink-0" />
                  <div className="min-w-0 flex-1 text-xs">
                    <div className="flex flex-wrap items-center gap-x-2">
                      <RefLink href={`/assessments/${a.id}`}>{a.ref}</RefLink>
                      <span className="text-muted-foreground">
                        {a.run_ref} · {formatDateTime(a.assessed_at)}
                      </span>
                      {a.id === data.first_assessment_id && <span className="rounded bg-red-100 px-1.5 text-[10px] text-red-700">first failure</span>}
                      {a.id === data.validated_by?.id && (
                        <span className="rounded bg-emerald-100 px-1.5 text-[10px] text-emerald-700">validated resolution</span>
                      )}
                    </div>
                    <p className="mt-0.5">{a.explanation}</p>
                  </div>
                </li>
              ))}
            </ol>
          </SectionCard>

          <SectionCard title="Activity history" description="Every workflow change is recorded with its actor" bodyClassName="p-0">
            {canEdit && !resolved && (
              <div className="border-b p-3">
                <NoteBox id={id} />
              </div>
            )}
            {data.activity.length === 0 ? (
              <EmptyState title="No activity yet" />
            ) : (
              <ol className="relative space-y-0 px-4 py-3">
                {data.activity.map((a) => (
                  <li key={a.id} className="relative flex gap-3 pb-4 last:pb-0">
                    <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", ACTIVITY_DOT[a.type] ?? "bg-slate-400")} />
                    <div className="min-w-0 flex-1 text-sm">
                      <p>{a.message}</p>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {a.actor?.full_name ?? "Control engine"} · {formatDateTime(a.created_at)}
                        {a.assessment_id && (
                          <>
                            {" · "}
                            <Link href={`/assessments/${a.assessment_id}`} className="text-blue-700 hover:underline">
                              assessment
                            </Link>
                          </>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </SectionCard>
        </div>

        <div className="space-y-4">
          <SectionCard title="Context">
            <dl className="grid grid-cols-1 gap-3">
              <Field label="Control">
                <RefLink href={`/controls/${data.control.id}`}>{data.control.id}</RefLink> {data.control.name}
              </Field>
              <Field label="Asset">
                <RefLink href={`/assets/${data.asset.id}`}>{data.asset.id}</RefLink> {data.asset.name}
                <div className="text-xs font-normal text-muted-foreground">
                  {data.asset.asset_type} · {data.asset.criticality} · {data.asset.environment}
                  {data.asset.internet_exposed ? " · internet-facing" : ""}
                </div>
              </Field>
              <Field label="Remediation owner">{f.assigned_owner?.full_name ?? "Unassigned"}</Field>
              <Field label="Control owner">{data.control.owner?.full_name ?? "—"}</Field>
              <Field label="Last seen failing">{formatDateTime(f.last_seen_at)}</Field>
              <Field label="Latest assessment">
                {data.latest_assessment ? (
                  <span className="flex items-center gap-2">
                    <RefLink href={`/assessments/${data.latest_assessment.id}`}>{data.latest_assessment.ref}</RefLink>
                    <StatusBadge status={data.latest_assessment.result} />
                  </span>
                ) : (
                  "—"
                )}
              </Field>
            </dl>
          </SectionCard>

          <SectionCard
            title="Potentially impacted services"
            description="Services whose dependency path includes this asset"
            actions={
              <Link href={`/services?asset=${data.asset.id}`} className="text-xs font-medium text-blue-700 hover:underline">
                View on map
              </Link>
            }
            bodyClassName="p-0"
          >
            {data.impacted_services.length === 0 ? (
              <EmptyState title="No dependent business services" />
            ) : (
              <ul className="divide-y">
                {data.impacted_services.map((s) => (
                  <li key={s.id} className="flex items-center justify-between px-4 py-2 text-sm">
                    <Link href={`/services/${s.id}`} className="hover:underline">
                      {s.name}
                    </Link>
                    <span className="rounded bg-muted px-1.5 text-[10px] font-medium text-muted-foreground">{s.tier}</span>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title="Remediation actions" bodyClassName="p-0">
            {data.actions.length === 0 ? (
              <EmptyState title="No actions recorded" />
            ) : (
              <ul className="divide-y">
                {data.actions.map((a) => (
                  <ActionRow key={a.id} a={a} canEdit={canEdit && !resolved} />
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title="Evidence" description="Evidence used by recent assessments" bodyClassName="p-0">
            {data.evidence.length === 0 ? (
              <EmptyState title="No evidence linked" />
            ) : (
              <ul className="divide-y">
                {data.evidence.map((e) => (
                  <li key={e.id} className="px-4 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <RefLink href={`/evidence/${e.id}`}>{e.ref}</RefLink>
                      <ValidationBadge status={e.validation_status} />
                    </div>
                    <div className="mt-0.5 truncate text-muted-foreground">
                      {e.original_filename} · collected {formatDate(e.collected_at)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {canEdit && !resolved && (
              <div className="border-t px-4 py-2 text-xs">
                <Link href={`/evidence?upload=1&asset_id=${f.asset_id}&control_id=${f.control_id}`} className="font-medium text-blue-700 hover:underline">
                  Upload updated evidence →
                </Link>
              </div>
            )}
          </SectionCard>

          <SectionCard title="Linked risks" bodyClassName="p-0">
            {data.risks.length === 0 ? (
              <EmptyState title="Not mapped to a risk" />
            ) : (
              <ul className="divide-y">
                {data.risks.map((r) => (
                  <li key={r.id} className="px-4 py-2 text-sm">
                    <RefLink href={`/risks/${r.id}`}>{r.id}</RefLink> <span>{r.title}</span>
                    <div className="text-xs text-muted-foreground">Residual rating: {r.residual_rating}</div>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          {can(PERM.INTEL) && <AssistantPanel findingId={f.id} />}

          {!canEdit && !resolved && (
            <p className="flex gap-1.5 text-xs text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              Your role can view this finding but not change it. Permissions are enforced by the API.
            </p>
          )}
        </div>
      </div>

      {dialog === "status" && <StatusDialog id={id} f={f} open onOpenChange={(o) => !o && setDialog(null)} />}
      {dialog === "accept" && <AcceptRiskDialog id={id} f={f} open onOpenChange={(o) => !o && setDialog(null)} />}
      {dialog === "assign" && <AssignDialog id={id} f={f} open onOpenChange={(o) => !o && setDialog(null)} />}
      {dialog === "action" && <ActionDialog id={id} open onOpenChange={(o) => !o && setDialog(null)} />}
    </div>
  );
}
