"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function AppHeader() {
  const pathname = usePathname();
  const isGenerate = pathname === "/";
  const isHealth = pathname.startsWith("/system/health");

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="container-page flex items-center justify-between py-4">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold">Innovex CO-DE-GEN</h1>
          <p className="text-xs text-slate-500">Innovex Company Detail Generator</p>
        </div>
        <nav className="flex items-center gap-2 text-sm">
          <Link
            className={`rounded-md px-3 py-1.5 transition ${isGenerate ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}
            href="/"
          >
            Generate
          </Link>
          <Link
            className={`rounded-md px-3 py-1.5 transition ${isHealth ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}
            href="/system/health"
          >
            System Health
          </Link>
        </nav>
      </div>
    </header>
  );
}

