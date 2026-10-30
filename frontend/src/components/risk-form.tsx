"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/common";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { useMeta, useUsers } from "@/lib/hooks";
import type { ServiceRef, UserRef } from "@/lib/types";
import { cn } from "@/lib/utils";

export type RiskSummary = {
  id: string;
  title: string;
  description: string;
  category: string;
  owner: UserRef;
  inherent_rating: string;
  residual_rating: string;
  treatment: string;
  treatment_plan: string;
  review_date: string;
  status: string;
  updated_at: string;
  control_ids: string[];
  services: ServiceRef[];
  finding_count: number;
  active_finding_count: number;
  max_active_score: number;
};

type Form = {
  title: string;
  description: string;
  category: string;
  owner_id: string;
  inherent_rating: string;
  residual_rating: string;
  treatment: string;
  treatment_plan: string;
  review_date: string;
  status: string;
  control_ids: string[];
  service_ids: string[];
};

function Chips({ options, value, onChange }: { options: { value: string; label: string }[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <button
            type="button"
            key={o.value}
            onClick={() => onChange(on ? value.filter((x) => x !== o.value) : [...value, o.value])}
            className={cn(
              "rounded-md border px-2 py-1 text-xs",
              on ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function RiskFormDialog({
  open,
  onOpenChange,
  risk,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  risk?: RiskSummary;
  onSaved?: (id: string) => void;
}) {
  const meta = useMeta();
  const users = useUsers();
  const qc = useQueryClient();
  const [form, setForm] = useState<Form>(() => ({
    title: risk?.title ?? "",
    description: risk?.description ?? "",
    category: risk?.category ?? "",
    owner_id: risk?.owner ? String(risk.owner.id) : "",
    inherent_rating: risk?.inherent_rating ?? "",
    residual_rating: risk?.residual_rating ?? "",
    treatment: risk?.treatment ?? "Mitigate",
    treatment_plan: risk?.treatment_plan ?? "",
    review_date: (risk?.review_date ?? new Date(Date.now() + 90 * 86400000).toISOString()).slice(0, 10),
    status: risk?.status ?? "Open",
    control_ids: risk?.control_ids ?? [],
    service_ids: risk?.services.map((s) => s.id) ?? [],
  }));
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));

  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...form,
        owner_id: form.owner_id ? Number(form.owner_id) : null,
        review_date: `${form.review_date}T00:00:00Z`,
      };
      return risk
        ? api<{ id: string }>(`/risks/${risk.id}`, { method: "PATCH", body })
        : api<{ id: string }>("/risks", { method: "POST", body });
    },
    onSuccess: (r) => {
      toast.success(risk ? `${risk.id} updated` : `Risk ${r.id} created`);
      qc.invalidateQueries();
      onOpenChange(false);
      onSaved?.(r.id ?? risk?.id ?? "");
    },
    onError: (e: Error) => toast.error("Risk not saved", { description: e.message }),
  });

  const valid =
    form.title.trim().length >= 5 &&
    form.description.trim().length >= 10 &&
    form.category &&
    form.inherent_rating &&
    form.residual_rating &&
    form.treatment &&
    form.review_date;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{risk ? `Edit ${risk.id}` : "Register technology risk"}</DialogTitle>
          <DialogDescription>Map the risk to the controls that mitigate it and the business services it threatens.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Title</Label>
            <Input value={form.title} onChange={(e) => set("title", e.target.value)} maxLength={255} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Description</Label>
            <Textarea value={form.description} onChange={(e) => set("description", e.target.value)} rows={3} maxLength={4000} />
          </div>
          <div className="space-y-1.5">
            <Label>Category</Label>
            <SimpleSelect value={form.category} onChange={(v) => set("category", v)} options={meta.data?.risk_categories ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Risk owner</Label>
            <SimpleSelect
              value={form.owner_id}
              onChange={(v) => set("owner_id", v)}
              options={(users.data ?? []).map((u) => ({ value: String(u.id), label: u.full_name }))}
              placeholder="Unassigned"
              className="w-full"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Inherent rating</Label>
            <SimpleSelect value={form.inherent_rating} onChange={(v) => set("inherent_rating", v)} options={meta.data?.risk_ratings ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Residual rating</Label>
            <SimpleSelect value={form.residual_rating} onChange={(v) => set("residual_rating", v)} options={meta.data?.risk_ratings ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Treatment</Label>
            <SimpleSelect value={form.treatment} onChange={(v) => set("treatment", v)} options={meta.data?.treatments ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Status</Label>
            <SimpleSelect value={form.status} onChange={(v) => set("status", v)} options={meta.data?.risk_statuses ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Next review</Label>
            <Input type="date" value={form.review_date} onChange={(e) => set("review_date", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Treatment plan</Label>
            <Textarea value={form.treatment_plan} onChange={(e) => set("treatment_plan", e.target.value)} rows={2} maxLength={4000} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Mitigating controls</Label>
            <Chips
              options={(meta.data?.controls ?? []).map((c) => ({ value: c.id, label: `${c.id} ${c.name}` }))}
              value={form.control_ids}
              onChange={(v) => set("control_ids", v)}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Business services at risk</Label>
            <Chips
              options={(meta.data?.services ?? []).map((s) => ({ value: s.id, label: s.name }))}
              value={form.service_ids}
              onChange={(v) => set("service_ids", v)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Spinner className="size-3.5" />} {risk ? "Save changes" : "Create risk"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
