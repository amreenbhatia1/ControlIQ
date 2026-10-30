"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Boxes,
  Brain,
  FileBarChart,
  FileCheck2,
  LayoutDashboard,
  Network,
  Settings,
  ShieldCheck,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";

export const NAV = [
  { href: "/", label: "Executive Overview", icon: LayoutDashboard },
  { href: "/controls", label: "Control Monitoring", icon: ShieldCheck },
  { href: "/assets", label: "Technology Assets", icon: Boxes },
  { href: "/services", label: "Business Services", icon: Network },
  { href: "/risks", label: "Risk Register", icon: ShieldAlert },
  { href: "/findings", label: "Findings & Remediation", icon: Wrench },
  { href: "/evidence", label: "Evidence Center", icon: FileCheck2 },
  { href: "/intelligence", label: "Risk Intelligence", icon: Brain },
  { href: "/reports", label: "Reports", icon: FileBarChart },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  if (href === "/controls" && pathname.startsWith("/assessments")) return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground lg:flex">
      <div className="flex h-14 items-center gap-2.5 border-b border-sidebar-border px-4">
        <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-400 to-blue-600 shadow-sm">
          <ShieldCheck className="size-4.5 text-white" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight text-white">ControlIQ</div>
          <div className="text-[10px] text-sidebar-foreground/70">Alpha Beta Bank</div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3" aria-label="Primary">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] font-medium transition-colors",
                active
                  ? "bg-sidebar-accent text-white shadow-[inset_2px_0_0_0] shadow-sky-400"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-white",
              )}
            >
              <Icon className={cn("size-4", active ? "text-sky-300" : "text-sidebar-foreground/60 group-hover:text-sky-200")} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-sidebar-border px-4 py-3 text-[10px] leading-relaxed text-sidebar-foreground/60">
        Continuous Technology Controls Monitoring &amp; Risk Intelligence
        <div className="mt-1 text-sidebar-foreground/40">v1.0 · Synthetic demo build</div>
      </div>
    </aside>
  );
}
