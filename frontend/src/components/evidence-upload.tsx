"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { JsonView, Spinner, ValidationBadge } from "@/components/common";
import { SimpleSelect } from "@/components/simple-select";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { useCan, useMeta, useRunAssessment } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import type { Evidence } from "@/lib/types";

export type EvidenceCategory = {
  key: string;
  label: string;
  structured: boolean;
  fields: string[];
  csv_list_field: string | null;
  sample: Record<string, unknown> | null;
};

const MAX_BYTES = 2 * 1024 * 1024;
const ACCEPT = ".json,.csv,.pdf,.txt,.log";

export function useEvidenceCategories() {
  return useQuery({
    queryKey: ["evidence-categories"],
    queryFn: () => api<EvidenceCategory[]>("/evidence/categories"),
    staleTime: 10 * 60_000,
  });
}

function downloadTemplate(category: EvidenceCategory, assetId: string) {
  const sample = { ...(category.sample ?? {}), ...(assetId ? { asset_id: assetId } : {}) };
  const blob = new Blob([JSON.stringify(sample, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${category.key}_template.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function EvidenceUploadDialog({
  open,
  onOpenChange,
  defaults,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  defaults?: { asset_id?: string; control_id?: string };
}) {
  const meta = useMeta();
  const can = useCan();
  const categories = useEvidenceCategories();
  const qc = useQueryClient();
  const run = useRunAssessment();
  const fileRef = useRef<HTMLInputElement>(null);
  const defaultCategory = defaults?.control_id ? meta.data?.controls.find((c) => c.id === defaults.control_id)?.evidence_category : undefined;
  const [category, setCategory] = useState(defaultCategory ?? "");
  const [assetId, setAssetId] = useState(defaults?.asset_id ?? "");
  const [controlId, setControlId] = useState(defaults?.control_id ?? "");
  const [source, setSource] = useState("Manual upload");
  const [collectedAt, setCollectedAt] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Evidence | null>(null);

  const effectiveCategory = category || defaultCategory || "";
  const cat = categories.data?.find((c) => c.key === effectiveCategory);
  const ext = file?.name.split(".").pop()?.toLowerCase() ?? "";
  const fileError = !file
    ? null
    : !["json", "csv", "pdf", "txt", "log"].includes(ext)
      ? "Only JSON, CSV, PDF, TXT or LOG files are accepted"
      : file.size > MAX_BYTES
        ? "File exceeds the 2 MB limit"
        : file.size === 0
          ? "File is empty"
          : null;

  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("file", file!);
      form.append("category", effectiveCategory);
      form.append("asset_id", assetId.trim().toUpperCase());
      form.append("source", source.trim() || "Manual upload");
      if (controlId) form.append("control_id", controlId);
      if (collectedAt) form.append("collected_at", new Date(collectedAt).toISOString());
      form.append("description", description);
      return api<Evidence>("/evidence/upload", { method: "POST", form });
    },
    onSuccess: (ev) => {
      setResult(ev);
      qc.invalidateQueries({ queryKey: ["evidence"] });
      qc.invalidateQueries({ queryKey: ["demo-status"] });
      if (ev.validation_status === "Invalid") toast.warning(`${ev.ref} stored but failed schema validation`);
      else toast.success(`${ev.ref} uploaded`, { description: `SHA-256 ${ev.sha256.slice(0, 16)}…` });
    },
    onError: (e: Error) => toast.error("Upload rejected", { description: e.message }),
  });

  const valid = effectiveCategory && assetId.trim() && file && !fileError;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Upload evidence</DialogTitle>
          <DialogDescription>
            Files are validated against the category schema, hashed with SHA-256 and stored immutably. Uploaded content is treated
            as untrusted data — it is never executed or followed as instructions. Evidence takes effect at the next assessment run.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="space-y-3 text-sm">
            <div className="flex items-center gap-2">
              <Link href={`/evidence/${result.id}`} className="mono font-semibold text-blue-700 hover:underline">
                {result.ref}
              </Link>
              <ValidationBadge status={result.validation_status} />
              <span className="text-xs text-muted-foreground">
                {result.original_filename} · {formatBytes(result.size_bytes)}
              </span>
            </div>
            <div className="mono text-xs break-all text-muted-foreground">sha256 {result.sha256}</div>
            {result.validation_errors.length > 0 && (
              <ul className="list-disc space-y-0.5 rounded-md border border-red-200 bg-red-50 p-3 pl-6 text-xs text-red-800">
                {result.validation_errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
            {result.validation_status === "Valid" && (
              <p className="text-xs text-muted-foreground">
                Run a control assessment to evaluate {result.asset_id} against this evidence. Until then, findings and dashboard
                figures are unchanged.
              </p>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label>Evidence category</Label>
              <SimpleSelect
                value={effectiveCategory}
                onChange={setCategory}
                options={(categories.data ?? []).map((c) => ({ value: c.key, label: c.label }))}
                placeholder="Select category"
                className="w-full"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ev-asset">Asset ID</Label>
              <Input id="ev-asset" value={assetId} onChange={(e) => setAssetId(e.target.value.toUpperCase())} placeholder="e.g. IDP-CORE-001" />
            </div>
            <div className="space-y-1.5">
              <Label>Control (optional)</Label>
              <SimpleSelect
                value={controlId}
                onChange={setControlId}
                options={(meta.data?.controls ?? []).map((c) => ({ value: c.id, label: `${c.id} ${c.name}` }))}
                allLabel="Not specified"
                className="w-full"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ev-source">Source system</Label>
              <Input id="ev-source" value={source} onChange={(e) => setSource(e.target.value)} maxLength={160} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ev-collected">Collected at (defaults to now)</Label>
              <Input id="ev-collected" type="datetime-local" value={collectedAt} onChange={(e) => setCollectedAt(e.target.value)} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="ev-description">Description</Label>
              <Textarea id="ev-description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} maxLength={2000} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="ev-file">File</Label>
              <input
                id="ev-file"
                ref={fileRef}
                type="file"
                accept={ACCEPT}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm file:mr-3 file:rounded-md file:border file:bg-muted file:px-3 file:py-1 file:text-sm"
              />
              {file && (
                <div className={fileError ? "text-xs text-red-600" : "text-xs text-muted-foreground"}>
                  {fileError ?? `${file.name} · ${formatBytes(file.size)}`}
                </div>
              )}
            </div>
            {cat && (
              <div className="space-y-1.5 rounded-md border bg-muted/30 p-3 sm:col-span-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs">
                    {cat.structured ? (
                      <>
                        Required fields: <span className="mono">{cat.fields.join(", ")}</span>
                        {cat.csv_list_field && (
                          <span className="block text-muted-foreground">
                            CSV uploads map each row to <span className="mono">{cat.csv_list_field}</span>.
                          </span>
                        )}
                      </>
                    ) : (
                      "Unstructured supporting document (PDF or text). Stored and hashed but not machine-evaluated."
                    )}
                  </div>
                  {cat.sample && (
                    <Button size="sm" variant="outline" onClick={() => downloadTemplate(cat, assetId.trim().toUpperCase())}>
                      <Download className="size-3.5" /> Template
                    </Button>
                  )}
                </div>
                {cat.sample && (
                  <>
                    <div className="text-[11px] text-muted-foreground">Format reference (synthetic example, not evidence):</div>
                    <JsonView value={cat.sample} className="max-h-48" />
                  </>
                )}
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          {result ? (
            <>
              <Button variant="outline" onClick={() => setResult(null)}>
                Upload another
              </Button>
              {can(PERM.ASSESSMENTS_RUN) && result.validation_status === "Valid" && (
                <Button
                  onClick={() => run.mutate(result.control_id ? [result.control_id] : undefined, { onSuccess: () => onOpenChange(false) })}
                  disabled={run.isPending}
                >
                  {run.isPending && <Spinner className="size-3.5" />} Run assessment now
                </Button>
              )}
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button disabled={!valid || upload.isPending} onClick={() => upload.mutate()}>
                {upload.isPending ? <Spinner className="size-3.5" /> : <Upload className="size-3.5" />} Upload
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
