"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getRunStatus, retryRun } from "@/lib/api";
import { ErrorCard } from "@/components/ErrorCard";
import { PageNav } from "@/components/PageNav";
import { RunSummaryCard } from "@/components/RunSummaryCard";
import { Timeline } from "@/components/Timeline";
import { useRunHistoryStore } from "@/store/runHistory";

const POLL_MS = Number(process.env.NEXT_PUBLIC_POLL_INTERVAL_MS || 3000);

export default function RunStatusPage() {
  const params = useParams<{ runId: string }>();
  const router = useRouter();
  const runId = params.runId;
  const upsertRun = useRunHistoryStore((s) => s.upsertRun);

  const query = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRunStatus(runId),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (status === "succeeded" || status === "failed") return false;
      return POLL_MS;
    },
    enabled: Boolean(runId),
  });

  const run = query.data;
  useEffect(() => {
    if (!run) return;
    upsertRun({
      run_id: run.run_id,
      company_name: run.company_name,
      status: run.status,
      timestamp: new Date().toISOString(),
    });
  }, [run?.run_id, run?.company_name, run?.status, upsertRun]);

  const onRetry = async () => {
    if (!runId) return;
    const retried = await retryRun(runId);
    router.push(`/runs/${retried.run_id}`);
  };

  return (
    <div className="space-y-4">
      <PageNav
        items={[
          { href: "/", label: "Generate" },
          { href: `/runs/${runId}`, label: "Run Status", active: true },
          { href: `/runs/${runId}/result`, label: "Result", disabled: run?.status !== "succeeded" },
          { href: "/system/health", label: "System Health" },
        ]}
      />
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Run Status</h2>
        <p className="font-mono text-xs text-slate-500">{runId}</p>
      </div>

      {query.isLoading && <div className="card">Loading run status...</div>}
      <ErrorCard error={query.error} />
      {run && <RunSummaryCard run={run} />}
      {run && <Timeline status={run.status} events={run.events} />}

      {run?.status === "queued" && <div className="card text-sm text-slate-600">Run queued. Waiting for execution.</div>}
      {run?.status === "running" && <div className="card text-sm text-blue-700">Run is executing. Polling live updates...</div>}

      <div className="flex gap-2">
        {run?.status === "succeeded" && <Link className="rounded-md bg-green-600 px-3 py-2 text-sm text-white" href={`/runs/${runId}/result`}>View Result</Link>}
        {run?.status === "failed" && <button className="rounded-md bg-red-600 px-3 py-2 text-sm text-white" onClick={onRetry}>Retry Generation</button>}
      </div>
    </div>
  );
}
