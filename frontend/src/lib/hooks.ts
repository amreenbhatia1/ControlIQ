"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "./api";
import type { Me, Meta, Page, Run, UserListItem } from "./types";

export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: () => api<UserListItem[]>("/users"), staleTime: 5 * 60_000 });
}

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/auth/me"), staleTime: 60_000 });
}

export function useCan() {
  const { data } = useMe();
  const perms = new Set(data?.role.permissions ?? []);
  return (perm: string) => perms.has(perm);
}

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/meta"), staleTime: 5 * 60_000 });
}

export function useLastRun() {
  return useQuery({
    queryKey: ["runs", "latest"],
    queryFn: () => api<Page<Run>>("/assessments/runs", { params: { page_size: 1 } }),
    select: (p) => p.items[0] ?? null,
  });
}

/** Run the control engine. All queries are invalidated afterwards so every view reflects the new state. */
export function useRunAssessment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (controlIds?: string[]) =>
      api<Run>("/assessments/run", { method: "POST", body: controlIds?.length ? { control_ids: controlIds } : {} }),
    onSuccess: (run) => {
      const s = run.summary;
      const parts = [
        `${s.scopes_evaluated} control instances evaluated`,
        s.findings_created.length ? `${s.findings_created.length} new finding(s)` : null,
        s.findings_resolved.length ? `${s.findings_resolved.length} resolved` : null,
        s.findings_pending_validation.length ? `${s.findings_pending_validation.length} pending validation` : null,
        s.status_changes.length ? `${s.status_changes.length} status change(s)` : null,
      ].filter(Boolean);
      toast.success(`Assessment ${run.ref} completed`, { description: parts.join(" · ") });
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error("Assessment run failed", { description: e.message }),
  });
}
