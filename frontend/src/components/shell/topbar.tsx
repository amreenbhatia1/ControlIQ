"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Bell, Clock, FlaskConical, LogOut, Menu, Search, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { formatDateTime, relativeTime, SEVERITY_COLORS } from "@/lib/format";
import { useLastRun, useMe } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { NAV, isActive } from "./sidebar";
import { usePathname } from "next/navigation";

type SearchHit = { type: string; id: string; title: string; subtitle: string; href: string };
type Notification = {
  id: number;
  type: string;
  title: string;
  message: string;
  severity: string;
  href: string;
  created_at: string;
};

function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api<SearchHit[]>("/search", { params: { q: debounced } }),
    enabled: debounced.length >= 2,
  });
  const hits = data ?? [];

  const go = (hit: SearchHit) => {
    setOpen(false);
    setQ("");
    router.push(hit.href);
  };

  return (
    <div ref={boxRef} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setCursor(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, hits.length - 1));
          if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
          if (e.key === "Enter" && hits[cursor]) go(hits[cursor]);
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Search controls, assets, findings, services, risks…"
        aria-label="Global search"
        className="h-9 w-full rounded-lg border bg-muted/40 pr-3 pl-8 text-sm outline-none placeholder:text-muted-foreground focus:border-ring focus:bg-background focus:ring-2 focus:ring-ring/20"
      />
      {open && debounced.length >= 2 && (
        <div className="absolute top-11 left-0 z-50 w-full overflow-hidden rounded-lg border bg-popover shadow-lg">
          {isFetching && hits.length === 0 ? (
            <div className="px-3 py-3 text-xs text-muted-foreground">Searching…</div>
          ) : hits.length === 0 ? (
            <div className="px-3 py-3 text-xs text-muted-foreground">No matches for “{debounced}”.</div>
          ) : (
            <ul className="max-h-80 overflow-y-auto py-1">
              {hits.map((h, i) => (
                <li key={`${h.type}-${h.id}`}>
                  <button
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => go(h)}
                    className={cn("flex w-full items-center gap-3 px-3 py-2 text-left", i === cursor && "bg-accent")}
                  >
                    <span className="w-16 shrink-0 rounded bg-muted px-1.5 py-0.5 text-center text-[10px] font-medium text-muted-foreground uppercase">
                      {h.type}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{h.title}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {h.id} · {h.subtitle}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Notifications() {
  const router = useRouter();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<Notification[]>("/notifications"),
    refetchInterval: 60_000,
  });
  const items = data ?? [];
  const recent = items.filter((n) => Date.now() - new Date(n.created_at).getTime() < 7 * 86400_000).length;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="Notifications" className="relative" />}>
        <Bell className="size-4.5" />
        {recent > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {recent}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-96">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Control events</DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        {items.length === 0 && <div className="px-2 py-4 text-center text-xs text-muted-foreground">No recent events</div>}
        {items.slice(0, 8).map((n) => (
          <DropdownMenuItem key={n.id} onClick={() => router.push(n.href)} className="items-start gap-2.5 py-2">
            <span className="mt-1.5 size-2 shrink-0 rounded-full" style={{ backgroundColor: SEVERITY_COLORS[n.severity] ?? "#64748b" }} />
            <span className="min-w-0">
              <span className="block text-xs font-semibold">{n.title}</span>
              <span className="block truncate text-xs text-muted-foreground">{n.message}</span>
              <span className="block text-[10px] text-muted-foreground">{relativeTime(n.created_at)}</span>
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Profile() {
  const { data: me } = useMe();
  const signOut = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    window.location.href = "/login";
  };
  const initials = (me?.full_name ?? "?")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<button className="flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-muted" aria-label="Profile menu" />}
      >
        <span className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
          {initials}
        </span>
        <span className="hidden text-left leading-tight md:block">
          <span className="block text-xs font-semibold">{me?.full_name}</span>
          <span className="block text-[11px] text-muted-foreground">{me?.role.name}</span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuGroup>
          <DropdownMenuLabel>
            <div className="text-sm font-semibold text-foreground">{me?.full_name}</div>
            <div className="text-xs font-normal">{me?.title}</div>
            <div className="text-xs font-normal">{me?.email}</div>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <div className="px-2 py-1.5 text-xs text-muted-foreground">
          <User className="mr-1 inline size-3" /> Role: <span className="font-medium text-foreground">{me?.role.name}</span>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={signOut}>
          <LogOut className="size-4" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" />}>
        <Menu className="size-5" />
      </SheetTrigger>
      <SheetContent side="left" className="w-64 bg-sidebar p-0 text-sidebar-foreground">
        <SheetTitle className="px-4 pt-4 text-white">ControlIQ</SheetTitle>
        <nav className="space-y-0.5 p-2">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm",
                isActive(pathname, href) ? "bg-sidebar-accent text-white" : "hover:bg-sidebar-accent/60",
              )}
            >
              <Icon className="size-4" /> {label}
            </Link>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}

export function Topbar() {
  const { data: run } = useLastRun();
  return (
    <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex h-14 items-center gap-3 px-4 lg:px-6">
        <MobileNav />
        <GlobalSearch />
        <div className="ml-auto flex items-center gap-1.5">
          <Tooltip>
            <TooltipTrigger
              render={
                <Link
                  href={run ? `/controls?run=${run.id}` : "/controls"}
                  className="hidden items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted xl:flex"
                />
              }
            >
              <Clock className="size-3.5" />
              Last assessment: <span className="font-medium text-foreground">{run ? relativeTime(run.evaluated_at) : "—"}</span>
            </TooltipTrigger>
            <TooltipContent>
              {run ? `${run.ref} · ${formatDateTime(run.evaluated_at)} · ${run.triggered_by}` : "No assessment run yet"}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              render={
                <span className="hidden items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800 sm:inline-flex" />
              }
            >
              <FlaskConical className="size-3" /> DEMO ENVIRONMENT
            </TooltipTrigger>
            <TooltipContent>All data is synthetic and generated for demonstration purposes.</TooltipContent>
          </Tooltip>
          <Notifications />
          <Profile />
        </div>
      </div>
    </header>
  );
}
