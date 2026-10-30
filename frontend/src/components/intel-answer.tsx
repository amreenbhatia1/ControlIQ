"use client";

import Link from "next/link";
import { Bot, Cpu, Info } from "lucide-react";
import type { Citation, IntelAnswer } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const CITATION_HREF: Record<string, (id: string) => string> = {
  finding: (id) => `/findings/${id}`,
  control: (id) => `/controls/${id}`,
  asset: (id) => `/assets/${id}`,
  service: (id) => `/services/${id}`,
  risk: (id) => `/risks/${id}`,
  assessment: (id) => `/assessments/${id}`,
  evidence: (id) => `/evidence/${id}`,
  run: (id) => `/controls?run=${id}`,
  action: () => `/findings`,
};

/** Renders the answer as plain text structure (headings and bullets). Never interprets HTML. */
export function AnswerBody({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = (key: number) => {
    if (list.length) {
      blocks.push(
        <ul key={`ul-${key}`} className="ml-4 list-disc space-y-1">
          {list.map((li, i) => (
            <li key={i}>{renderInline(li)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  text.split("\n").forEach((raw, i) => {
    const line = raw.trimEnd();
    if (/^\s*[-•*]\s+/.test(line)) {
      list.push(line.replace(/^\s*[-•*]\s+/, ""));
      return;
    }
    flush(i);
    if (!line.trim()) return;
    const heading = line.match(/^#{1,4}\s+(.*)$/) ?? line.match(/^\*\*(.+)\*\*:?$/);
    if (heading) blocks.push(<div key={i} className="mt-2 font-semibold first:mt-0">{heading[1]}</div>);
    else if (/:$/.test(line) && line.length < 60) blocks.push(<div key={i} className="mt-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{line.replace(/:$/, "")}</div>);
    else blocks.push(<p key={i}>{renderInline(line)}</p>);
  });
  flush(-1);
  return <div className="space-y-1.5 text-sm leading-relaxed">{blocks}</div>;
}

function renderInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>,
  );
}

export function ModeBadge({ answer }: { answer: Pick<IntelAnswer, "mode" | "mode_label"> }) {
  const ai = answer.mode === "ai";
  return (
    <span
      className={cn(
        "badge-ring",
        ai ? "bg-violet-50 text-violet-700 ring-violet-600/20" : "bg-sky-50 text-sky-800 ring-sky-600/20",
      )}
    >
      {ai ? <Bot className="size-3" /> : <Cpu className="size-3" />}
      {answer.mode_label}
    </span>
  );
}

export function Citations({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {citations.map((c) => {
        const href = CITATION_HREF[c.type]?.(c.id);
        const inner = (
          <>
            <span className="mono font-semibold">{c.id}</span>
            <span className="max-w-48 truncate text-muted-foreground">{c.label}</span>
          </>
        );
        return href ? (
          <Link
            key={`${c.type}-${c.id}`}
            href={href}
            className="inline-flex items-center gap-1.5 rounded-md border bg-background px-2 py-0.5 text-[11px] hover:border-ring"
          >
            {inner}
          </Link>
        ) : (
          <span key={`${c.type}-${c.id}`} className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px]">
            {inner}
          </span>
        );
      })}
    </div>
  );
}

export function IntelAnswerView({ answer, compact }: { answer: IntelAnswer; compact?: boolean }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <ModeBadge answer={answer} />
        <span>
          Grounded in {answer.records_used} record{answer.records_used === 1 ? "" : "s"} · {formatDateTime(answer.generated_at)}
        </span>
      </div>
      {answer.notice && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          {answer.notice}
        </div>
      )}
      <AnswerBody text={compact ? answer.answer.split("\n").slice(0, 14).join("\n") : answer.answer} />
      {answer.citations.length > 0 && (
        <div>
          <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Sources</div>
          <Citations citations={answer.citations} />
        </div>
      )}
    </div>
  );
}
