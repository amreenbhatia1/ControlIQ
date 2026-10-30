"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/common";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/hooks";
import type { Asset } from "@/lib/types";

type FormState = {
  id: string;
  name: string;
  asset_type: string;
  description: string;
  business_owner: string;
  technical_owner: string;
  environment: string;
  criticality: string;
  internet_exposed: boolean;
  privileged_access_hub: boolean;
  has_redundancy: boolean;
  platform: string;
  lifecycle_status: string;
  service_ids: string[];
};

const EMPTY: FormState = {
  id: "",
  name: "",
  asset_type: "",
  description: "",
  business_owner: "",
  technical_owner: "",
  environment: "Production",
  criticality: "",
  internet_exposed: false,
  privileged_access_hub: false,
  has_redundancy: false,
  platform: "",
  lifecycle_status: "Active",
  service_ids: [],
};

export function AssetFormDialog({
  open,
  onOpenChange,
  asset,
  serviceIds,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  asset?: Asset;
  serviceIds?: string[];
  onSaved?: (a: Asset) => void;
}) {
  const meta = useMeta();
  const qc = useQueryClient();
  const editing = Boolean(asset);
  const [form, setForm] = useState<FormState>(() =>
    asset
      ? {
          id: asset.id,
          name: asset.name,
          asset_type: asset.asset_type,
          description: asset.description,
          business_owner: asset.business_owner,
          technical_owner: asset.technical_owner,
          environment: asset.environment,
          criticality: asset.criticality,
          internet_exposed: asset.internet_exposed,
          privileged_access_hub: asset.privileged_access_hub,
          has_redundancy: asset.has_redundancy,
          platform: asset.platform,
          lifecycle_status: asset.lifecycle_status,
          service_ids: serviceIds ?? [],
        }
      : EMPTY,
  );
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }));

  const save = useMutation({
    mutationFn: () => {
      if (editing) {
        const { id: _id, ...rest } = form;
        void _id;
        return api<Asset>(`/assets/${asset!.id}`, { method: "PATCH", body: rest });
      }
      return api<Asset>("/assets", { method: "POST", body: { ...form, id: form.id.trim().toUpperCase() } });
    },
    onSuccess: (a) => {
      toast.success(editing ? `${a.id} updated` : `${a.id} created`);
      qc.invalidateQueries();
      onOpenChange(false);
      onSaved?.(a);
    },
    onError: (e: Error) => toast.error("Asset not saved", { description: e.message }),
  });

  const idValid = editing || /^[A-Z0-9][A-Z0-9-]{2,38}$/.test(form.id.trim().toUpperCase());
  const valid =
    idValid &&
    form.name.trim().length >= 3 &&
    form.asset_type &&
    form.criticality &&
    form.business_owner.trim().length >= 2 &&
    form.technical_owner.trim().length >= 2;

  const toggleService = (sid: string) =>
    set("service_ids", form.service_ids.includes(sid) ? form.service_ids.filter((x) => x !== sid) : [...form.service_ids, sid]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editing ? `Edit ${asset!.id}` : "Register technology asset"}</DialogTitle>
          <DialogDescription>Changes are audited. Criticality and exposure feed directly into risk scoring on the next assessment.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Asset ID</Label>
            <Input
              value={form.id}
              disabled={editing}
              onChange={(e) => set("id", e.target.value.toUpperCase())}
              placeholder="e.g. PAY-API-002"
              aria-invalid={!idValid}
            />
            {!idValid && form.id && <p className="text-xs text-red-600">Use 3–39 uppercase letters, digits or hyphens.</p>}
          </div>
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} maxLength={160} />
          </div>
          <div className="space-y-1.5">
            <Label>Asset type</Label>
            <SimpleSelect value={form.asset_type} onChange={(v) => set("asset_type", v)} options={meta.data?.asset_types ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Criticality</Label>
            <SimpleSelect value={form.criticality} onChange={(v) => set("criticality", v)} options={meta.data?.criticality ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Environment</Label>
            <SimpleSelect value={form.environment} onChange={(v) => set("environment", v)} options={meta.data?.environments ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Lifecycle status</Label>
            <SimpleSelect value={form.lifecycle_status} onChange={(v) => set("lifecycle_status", v)} options={meta.data?.lifecycle ?? []} className="w-full" />
          </div>
          <div className="space-y-1.5">
            <Label>Business owner</Label>
            <Input value={form.business_owner} onChange={(e) => set("business_owner", e.target.value)} maxLength={120} />
          </div>
          <div className="space-y-1.5">
            <Label>Technical owner</Label>
            <Input value={form.technical_owner} onChange={(e) => set("technical_owner", e.target.value)} maxLength={120} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Platform</Label>
            <Input value={form.platform} onChange={(e) => set("platform", e.target.value)} maxLength={120} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Description</Label>
            <Textarea value={form.description} onChange={(e) => set("description", e.target.value)} rows={2} maxLength={2000} />
          </div>
          <div className="flex flex-wrap gap-5 sm:col-span-2">
            {(
              [
                ["internet_exposed", "Internet-facing"],
                ["privileged_access_hub", "Privileged access hub"],
                ["has_redundancy", "Redundant / failover"],
              ] as const
            ).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-sm">
                <Switch checked={form[k]} onCheckedChange={(v) => set(k, Boolean(v))} />
                {label}
              </label>
            ))}
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Directly supports business services</Label>
            <div className="flex flex-wrap gap-1.5">
              {(meta.data?.services ?? []).map((s) => {
                const on = form.service_ids.includes(s.id);
                return (
                  <button
                    type="button"
                    key={s.id}
                    onClick={() => toggleService(s.id)}
                    className={
                      on
                        ? "rounded-md border border-primary bg-primary px-2 py-1 text-xs text-primary-foreground"
                        : "rounded-md border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                    }
                  >
                    {s.name}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Spinner className="size-3.5" />} {editing ? "Save changes" : "Create asset"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
