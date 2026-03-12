"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api";
import { ErrorCard } from "@/components/ErrorCard";
import { PageNav } from "@/components/PageNav";

export default function HealthPage() {
  const q = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 10000 });

  const badge = !q.data
    ? "bg-slate-200 text-slate-700"
    : q.data.status === "ok"
      ? "bg-green-100 text-green-700"
      : "bg-red-100 text-red-700";

  return (
    <div className="space-y-4">
      <PageNav
        items={[
          { href: "/", label: "Generate" },
          { href: "/system/health", label: "System Health", active: true },
        ]}
      />
      <h2 className="text-xl font-semibold">System Health</h2>
      <ErrorCard error={q.error} />
      <div className="card text-sm">
        <p>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${badge}`}>{q.data?.status || "unknown"}</span>
        </p>
        <p className="mt-2"><span className="text-slate-500">Pipeline Ready:</span> {String(q.data?.pipeline_ready ?? false)}</p>
        <p><span className="text-slate-500">Latency:</span> {q.data?.latencyMs ?? "-"} ms</p>
      </div>
    </div>
  );
}
