import { Info } from "lucide-react";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <div
          role="note"
          className="flex items-center justify-center gap-1.5 bg-amber-100 px-4 py-1 text-center text-xs font-medium text-amber-900"
        >
          <Info className="size-3.5 shrink-0" />
          Synthetic demonstration environment — no production banking data.
        </div>
        <Topbar />
        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 lg:px-6">{children}</main>
      </div>
    </div>
  );
}
