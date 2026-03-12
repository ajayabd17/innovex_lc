"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { getRunResult, getRunStatus, retryRun, downloadRunCsv, ApiError } from "@/lib/api";
import { ErrorCard } from "@/components/ErrorCard";
import { JsonExplorer } from "@/components/JsonExplorer";
import { PageNav } from "@/components/PageNav";
import { RenderedCompanyView } from "@/components/RenderedCompanyView";

export default function RunResultPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const router = useRouter();
  const [viewMode, setViewMode] = useState<"json" | "rendered">("json");
  const [downloadingCsv, setDownloadingCsv] = useState(false);

  const statusQuery = useQuery({ queryKey: ["run-status", runId], queryFn: () => getRunStatus(runId), enabled: Boolean(runId) });
  const resultQuery = useQuery({ queryKey: ["run-result", runId], queryFn: () => getRunResult(runId), enabled: Boolean(runId), retry: false });

  if (resultQuery.error instanceof ApiError && resultQuery.error.code === "RUN_NOT_READY") {
    router.replace(`/runs/${runId}`);
    return null;
  }

  const onRetry = async () => {
    const retried = await retryRun(runId);
    router.push(`/runs/${retried.run_id}`);
  };

  const onDownloadCsv = async () => {
    try {
      setDownloadingCsv(true);
      await downloadRunCsv(runId);
    } finally {
      setDownloadingCsv(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageNav
        items={[
          { href: "/", label: "Generate" },
          { href: `/runs/${runId}`, label: "Run Status" },
          { href: `/runs/${runId}/result`, label: "Result", active: true },
          { href: "/system/health", label: "System Health" },
        ]}
      />
      <h2 className="text-xl font-semibold">Run Result</h2>

      {statusQuery.data && (
        <div className="card grid gap-2 text-sm sm:grid-cols-2">
          <p><span className="text-slate-500">Run ID:</span> <span className="font-mono text-xs">{runId}</span></p>
          <p><span className="text-slate-500">Database ID:</span> <span className="font-mono text-xs">{statusQuery.data.database_id || "-"}</span></p>
          <p><span className="text-slate-500">Attempt:</span> {statusQuery.data.attempt}</p>
          <p><span className="text-slate-500">Completed:</span> {statusQuery.data.completed_at ? new Date(statusQuery.data.completed_at).toLocaleString() : "-"}</p>
        </div>
      )}

      <ErrorCard error={resultQuery.error} />

      {resultQuery.data?.result && (
        <>
          <div className="card text-sm">
            <p><span className="text-slate-500">Confidence:</span> {typeof resultQuery.data.result.confidence === "number" ? `${Math.round((resultQuery.data.result.confidence as number) * 100)}%` : "-"}</p>
            <div className="mt-3">
              <button
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                onClick={onDownloadCsv}
                disabled={downloadingCsv}
              >
                {downloadingCsv ? "Downloading CSV..." : "Download CSV"}
              </button>
            </div>
          </div>

          <div className="card">
            <div className="inline-flex rounded-lg border border-slate-300 bg-slate-100 p-1">
              <button
                className={`rounded-md px-3 py-1.5 text-sm ${viewMode === "json" ? "bg-white shadow-sm" : "text-slate-600"}`}
                onClick={() => setViewMode("json")}
              >
                JSON
              </button>
              <button
                className={`rounded-md px-3 py-1.5 text-sm ${viewMode === "rendered" ? "bg-white shadow-sm" : "text-slate-600"}`}
                onClick={() => setViewMode("rendered")}
              >
                Rendered
              </button>
            </div>
          </div>

          {viewMode === "json" ? (
            <JsonExplorer data={resultQuery.data.result} filename={`company_detail_${runId}.json`} />
          ) : (
            <RenderedCompanyView data={resultQuery.data.result as Record<string, unknown>} />
          )}
        </>
      )}

      {(statusQuery.data?.status === "failed" || (resultQuery.error instanceof ApiError && resultQuery.error.code === "PIPELINE_FAILED")) && (
        <button className="rounded-md bg-red-600 px-3 py-2 text-sm text-white" onClick={onRetry}>Retry Generation</button>
      )}
    </div>
  );
}
