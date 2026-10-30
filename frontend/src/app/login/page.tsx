"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Info, Lock, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/common";
import { api } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { email: "catherine.hale@alphabetabank.example", name: "Catherine Hale", role: "Executive Viewer", note: "Chief Technology Controls Officer" },
  { email: "priya.raman@alphabetabank.example", name: "Priya Raman", role: "Risk Analyst", note: "Runs assessments and manages findings" },
  { email: "daniel.okafor@alphabetabank.example", name: "Daniel Okafor", role: "Control Owner", note: "Owns IAM controls" },
  { email: "alex.morgan@alphabetabank.example", name: "Alex Morgan", role: "Administrator", note: "Configuration, audit log, demo reset" },
];

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { method: "POST", body: { email, password } });
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-sidebar p-10 text-sidebar-foreground lg:flex">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(56,189,248,0.18),transparent_55%)]" />
        <div className="relative flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-blue-600">
            <ShieldCheck className="size-5 text-white" />
          </div>
          <div>
            <div className="text-lg font-semibold text-white">ControlIQ</div>
            <div className="text-xs text-sidebar-foreground/70">Alpha Beta Bank</div>
          </div>
        </div>
        <div className="relative max-w-lg">
          <h1 className="text-3xl leading-tight font-semibold text-white">
            Continuous technology controls monitoring &amp; risk intelligence
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-sidebar-foreground/80">
            Evidence-based control assessments, explainable risk prioritisation and traceability from business service
            to remediation — in one place.
          </p>
          <ul className="mt-6 space-y-2 text-sm text-sidebar-foreground/80">
            <li>• Immutable, reproducible control assessments</li>
            <li>• Business-service dependency mapping and potential exposure</li>
            <li>• Remediation validated only against updated evidence</li>
          </ul>
        </div>
        <div className="relative text-xs text-sidebar-foreground/50">
          Synthetic demonstration environment — no production banking data.
        </div>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="mb-6 lg:hidden">
            <div className="text-xl font-semibold">ControlIQ</div>
            <div className="text-xs text-muted-foreground">Alpha Beta Bank</div>
          </div>
          <h2 className="text-xl font-semibold">Sign in</h2>
          <p className="mt-1 text-sm text-muted-foreground">Use one of the synthetic demo accounts below.</p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-10"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="h-10"
              />
            </div>
            {error && (
              <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}
            <Button type="submit" className="h-10 w-full" disabled={busy}>
              {busy ? <Spinner /> : <Lock className="size-4" />} Sign in
            </Button>
          </form>

          <div className="mt-8">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Info className="size-3.5" /> Demo accounts (password is set by <code className="mono">DEMO_PASSWORD</code>; default
              <code className="mono">ControlIQ-Demo-2026!</code>)
            </div>
            <div className="grid gap-2">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.email}
                  type="button"
                  onClick={() => setEmail(a.email)}
                  className="flex items-center justify-between rounded-lg border bg-card px-3 py-2 text-left hover:border-ring hover:bg-accent/50"
                >
                  <span>
                    <span className="block text-sm font-medium">{a.name}</span>
                    <span className="block text-xs text-muted-foreground">{a.note}</span>
                  </span>
                  <span className="rounded bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">{a.role}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
