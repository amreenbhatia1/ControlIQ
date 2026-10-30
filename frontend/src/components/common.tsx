"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  FINDING_STATUS_BADGE,
  SEVERITY_BADGE,
  STATUS_BADGE,
  VALIDATION_BADGE,
  scoreColor,
} from "@/lib/format";

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  eyebrow?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SeverityBadge({ severity, className }: { severity: string; className?: string }) {
  return <span className={cn("badge-ring", SEVERITY_BADGE[severity] ?? SEVERITY_BADGE.None, className)}>{severity}</span>;
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const dot =
    status === "Effective"
      ? "bg-emerald-500"
      : status === "Ineffective"
        ? "bg-red-500"
        : status === "Needs Review"
          ? "bg-amber-500"
          : "bg-slate-400";
  return (
    <span className={cn("badge-ring", STATUS_BADGE[status] ?? STATUS_BADGE["Not Assessed"], className)}>
      <span className={cn("size-1.5 rounded-full", dot)} />
      {status}
    </span>
  );
}

export function FindingStatusBadge({ status }: { status: string }) {
  return <span className={cn("badge-ring", FINDING_STATUS_BADGE[status] ?? FINDING_STATUS_BADGE.Open)}>{status}</span>;
}

export function ValidationBadge({ status }: { status: string }) {
  return <span className={cn("badge-ring", VALIDATION_BADGE[status] ?? VALIDATION_BADGE.Unstructured)}>{status}</span>;
}

export function ScorePill({ score }: { score: number }) {
  return (
    <span
      className="inline-flex h-6 min-w-9 items-center justify-center rounded-md px-1.5 text-xs font-semibold text-white tabular-nums"
      style={{ backgroundColor: scoreColor(score) }}
    >
      {score}
    </span>
  );
}

export function KpiCard({
  label,
  value,
  sub,
  icon: Icon,
  tone = "default",
  href,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  icon?: LucideIcon;
  tone?: "default" | "danger" | "warning" | "success";
  href?: string;
}) {
  const toneCls = {
    default: "text-slate-600 bg-slate-100",
    danger: "text-red-600 bg-red-50",
    warning: "text-amber-600 bg-amber-50",
    success: "text-emerald-600 bg-emerald-50",
  }[tone];
  const body = (
    <Card className="h-full gap-2 px-4 py-4 transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {Icon && (
          <span className={cn("rounded-md p-1.5", toneCls)}>
            <Icon className="size-4" />
          </span>
        )}
      </div>
      <div className="text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </Card>
  );
  return href ? (
    <Link href={href} className="block h-full rounded-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
      {body}
    </Link>
  ) : (
    body
  );
}

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <Card className={cn("gap-0 py-0", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </Card>
  );
}

export function EmptyState({ title, description, icon: Icon = Inbox }: { title: string; description?: string; icon?: LucideIcon }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <Icon className="size-8 text-muted-foreground/60" />
      <div className="text-sm font-medium">{title}</div>
      {description && <div className="max-w-sm text-xs text-muted-foreground">{description}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-red-200 bg-red-50/50 py-8 text-center">
      <AlertTriangle className="size-6 text-red-500" />
      <div className="text-sm font-medium text-red-700">Unable to load data</div>
      <div className="max-w-md text-xs text-red-600">{message}</div>
      {onRetry && (
        <button onClick={onRetry} className="mt-1 text-xs font-medium text-red-700 underline">
          Retry
        </button>
      )}
    </div>
  );
}

export function LoadingBlock({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin", className)} />;
}

export function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium break-words">{children}</dd>
    </div>
  );
}

export function RefLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="mono text-xs font-medium text-blue-700 hover:underline">
      {children}
    </Link>
  );
}

export function JsonView({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre className={cn("mono max-h-96 overflow-auto rounded-md border bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-100", className)}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function KeyValues({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined);
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-xs text-muted-foreground">{k.replaceAll("_", " ")}</dt>
          <dd className="mono mt-0.5 text-xs break-words">
            {typeof v === "object" ? JSON.stringify(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between gap-2 border-t px-4 py-2 text-xs text-muted-foreground">
      <span>
        {total === 0 ? "No records" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total.toLocaleString()}`}
      </span>
      <div className="flex items-center gap-1">
        <button
          className="rounded-md border px-2 py-1 disabled:opacity-40"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </button>
        <span className="px-2 tabular-nums">
          {page} / {pages}
        </span>
        <button
          className="rounded-md border px-2 py-1 disabled:opacity-40"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
