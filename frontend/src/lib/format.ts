const DATE_FMT = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const DATETIME_FMT = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : `${DATETIME_FMT.format(d)} UTC`;
}

export function relativeTime(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return "never";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  const seconds = Math.round((now.getTime() - d.getTime()) / 1000);
  const future = seconds < 0;
  const s = Math.abs(seconds);
  const units: [number, string][] = [
    [86400 * 365, "year"],
    [86400 * 30, "month"],
    [86400, "day"],
    [3600, "hour"],
    [60, "minute"],
  ];
  for (const [size, unit] of units) {
    if (s >= size) {
      const n = Math.floor(s / size);
      const label = `${n} ${unit}${n === 1 ? "" : "s"}`;
      return future ? `in ${label}` : `${label} ago`;
    }
  }
  return future ? "in under a minute" : "just now";
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function shortHash(hash: string, size = 12): string {
  return hash.length > size ? `${hash.slice(0, size)}…` : hash;
}

export function titleCase(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

export const SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"] as const;

export const SEVERITY_COLORS: Record<string, string> = {
  Critical: "#dc2626",
  High: "#ea580c",
  Medium: "#d97706",
  Low: "#64748b",
};

export const STATUS_COLORS: Record<string, string> = {
  Effective: "#059669",
  Ineffective: "#dc2626",
  "Needs Review": "#d97706",
  "Not Assessed": "#94a3b8",
};

export const SEVERITY_BADGE: Record<string, string> = {
  Critical: "bg-red-50 text-red-700 ring-red-600/20",
  High: "bg-orange-50 text-orange-700 ring-orange-600/20",
  Medium: "bg-amber-50 text-amber-700 ring-amber-600/20",
  Low: "bg-slate-100 text-slate-600 ring-slate-500/20",
  None: "bg-slate-50 text-slate-500 ring-slate-400/20",
};

export const STATUS_BADGE: Record<string, string> = {
  Effective: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  Ineffective: "bg-red-50 text-red-700 ring-red-600/20",
  "Needs Review": "bg-amber-50 text-amber-700 ring-amber-600/20",
  "Not Assessed": "bg-slate-100 text-slate-600 ring-slate-500/20",
};

export const FINDING_STATUS_BADGE: Record<string, string> = {
  Open: "bg-red-50 text-red-700 ring-red-600/20",
  "In Progress": "bg-blue-50 text-blue-700 ring-blue-600/20",
  "Pending Validation": "bg-violet-50 text-violet-700 ring-violet-600/20",
  "Risk Accepted": "bg-amber-50 text-amber-800 ring-amber-600/20",
  Resolved: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
};

export const VALIDATION_BADGE: Record<string, string> = {
  Valid: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  Invalid: "bg-red-50 text-red-700 ring-red-600/20",
  Unstructured: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

export function scoreColor(score: number): string {
  if (score >= 80) return SEVERITY_COLORS.Critical;
  if (score >= 60) return SEVERITY_COLORS.High;
  if (score >= 40) return SEVERITY_COLORS.Medium;
  return SEVERITY_COLORS.Low;
}
