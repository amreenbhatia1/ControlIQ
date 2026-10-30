"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

export type Option = { value: string; label: string };

const ALL = "__all__";

/** Thin wrapper over the shadcn/Base UI select with an optional "all" entry mapped to an empty value. */
export function SimpleSelect({
  value,
  onChange,
  options,
  placeholder,
  allLabel,
  className,
  disabled,
  id,
}: {
  value: string;
  onChange: (v: string) => void;
  options: (Option | string)[];
  placeholder?: string;
  allLabel?: string;
  className?: string;
  disabled?: boolean;
  id?: string;
}) {
  const opts: Option[] = options.map((o) => (typeof o === "string" ? { value: o, label: o } : o));
  const items = allLabel ? [{ value: ALL, label: allLabel }, ...opts] : opts;
  const current = value === "" && allLabel ? ALL : value || null;
  return (
    <Select
      items={items}
      value={current}
      disabled={disabled}
      onValueChange={(v) => onChange(v === ALL || v == null ? "" : String(v))}
    >
      <SelectTrigger id={id} className={cn("h-8 min-w-36 bg-background text-sm", className)}>
        <SelectValue placeholder={placeholder ?? "Select…"} />
      </SelectTrigger>
      <SelectContent>
        {items.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
