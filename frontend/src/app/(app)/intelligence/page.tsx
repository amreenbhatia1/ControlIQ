"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Cpu, Send, ShieldCheck, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, PageHeader, SectionCard, Spinner } from "@/components/common";
import { IntelAnswerView } from "@/components/intel-answer";
import { api } from "@/lib/api";
import type { IntelAnswer } from "@/lib/types";

type Status = { ai_enabled: boolean; mode: string; model: string | null; label: string; supported_questions: string[] };

type Turn = { id: number; question: string; answer?: IntelAnswer; error?: string };

export default function IntelligencePage() {
  const status = useQuery({ queryKey: ["intel-status"], queryFn: () => api<Status>("/intelligence/status") });
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (q: string) => api<IntelAnswer>("/intelligence/ask", { method: "POST", body: { question: q } }),
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const submit = (q: string) => {
    const text = q.trim();
    if (text.length < 3 || ask.isPending) return;
    const id = Date.now();
    setTurns((t) => [...t, { id, question: text }]);
    setQuestion("");
    ask.mutate(text, {
      onSuccess: (answer) => setTurns((t) => t.map((x) => (x.id === id ? { ...x, answer } : x))),
      onError: (e: Error) => setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: e.message } : x))),
    });
  };

  const s = status.data;

  return (
    <div>
      <PageHeader
        title="Risk Intelligence"
        description="Ask questions about the control environment. Answers are grounded only in stored assessments, findings, evidence metadata and remediation records, with sources cited."
      />
      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <SectionCard bodyClassName="flex h-[calc(100vh-260px)] min-h-[520px] flex-col p-0">
          <div className="flex-1 space-y-5 overflow-y-auto p-4">
            {turns.length === 0 && (
              <div className="mx-auto max-w-lg py-12 text-center">
                <Bot className="mx-auto size-10 text-muted-foreground/50" />
                <div className="mt-2 text-sm font-medium">Ask about controls, findings, services or remediation</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  The assistant cannot change records, approve risk acceptance or create evidence. Choose a suggested question to
                  start.
                </p>
              </div>
            )}
            {turns.map((t) => (
              <div key={t.id} className="space-y-3">
                <div className="flex justify-end">
                  <div className="flex max-w-[80%] items-start gap-2 rounded-xl bg-primary px-3 py-2 text-sm text-primary-foreground">
                    <User className="mt-0.5 size-3.5 shrink-0 opacity-70" />
                    {t.question}
                  </div>
                </div>
                <div className="max-w-[92%] rounded-xl border bg-muted/20 p-4">
                  {t.answer ? (
                    <IntelAnswerView answer={t.answer} />
                  ) : t.error ? (
                    <ErrorState error={new Error(t.error)} />
                  ) : (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Spinner /> Retrieving records…
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <form
            className="flex items-end gap-2 border-t p-3"
            onSubmit={(e) => {
              e.preventDefault();
              submit(question);
            }}
          >
            <Textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit(question);
                }
              }}
              rows={2}
              maxLength={1000}
              placeholder="e.g. Which business services are most exposed right now?"
              className="resize-none text-sm"
            />
            <Button type="submit" disabled={question.trim().length < 3 || ask.isPending}>
              {ask.isPending ? <Spinner /> : <Send className="size-4" />} Ask
            </Button>
          </form>
        </SectionCard>

        <div className="space-y-4">
          <SectionCard title="Mode">
            {status.error ? (
              <ErrorState error={status.error} />
            ) : s ? (
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2 font-medium">
                  {s.ai_enabled ? <Bot className="size-4 text-violet-600" /> : <Cpu className="size-4 text-sky-700" />}
                  {s.label}
                </div>
                <p className="text-xs text-muted-foreground">
                  {s.ai_enabled
                    ? `AI-assisted answers via ${s.model}. Each answer is generated from a retrieved record set and checked for references to records that do not exist; if the AI service fails, the answer is clearly labelled as rule-based.`
                    : "No AI provider is configured. Answers are deterministic, template-based summaries computed from stored records — no language model is involved."}
                </p>
              </div>
            ) : (
              <Spinner />
            )}
          </SectionCard>
          <SectionCard title="Suggested questions" bodyClassName="p-2">
            <ul className="space-y-1">
              {(s?.supported_questions ?? []).map((q) => (
                <li key={q}>
                  <button
                    onClick={() => submit(q)}
                    disabled={ask.isPending}
                    className="w-full rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted disabled:opacity-50"
                  >
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </SectionCard>
          <SectionCard
            title={
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="size-4" /> Guardrails
              </span>
            }
          >
            <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
              <li>Uploaded documents are treated as untrusted data; instructions inside them are ignored.</li>
              <li>The assistant never creates evidence, changes findings or approves risk acceptance.</li>
              <li>Every answer lists the records it relied on.</li>
              <li>Questions are recorded in the audit log.</li>
            </ul>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
