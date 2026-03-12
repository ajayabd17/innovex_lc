import type { RunStatusResponse } from "@/types/api";
import { StatusBadge } from "@/components/StatusBadge";

export function RunSummaryCard({ run }: { run: RunStatusResponse }) {
  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">Run Summary</h3>
        <StatusBadge status={run.status} />
      </div>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div><dt className="text-slate-500">Run ID</dt><dd className="font-mono text-xs break-all">{run.run_id}</dd></div>
        <div><dt className="text-slate-500">Company</dt><dd>{run.company_name}</dd></div>
        <div><dt className="text-slate-500">Attempt</dt><dd>{run.attempt}</dd></div>
        <div><dt className="text-slate-500">Database ID</dt><dd className="font-mono text-xs break-all">{run.database_id || "-"}</dd></div>
        <div><dt className="text-slate-500">Created</dt><dd>{new Date(run.created_at).toLocaleString()}</dd></div>
        <div><dt className="text-slate-500">Started</dt><dd>{run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</dd></div>
        <div><dt className="text-slate-500">Completed</dt><dd>{run.completed_at ? new Date(run.completed_at).toLocaleString() : "-"}</dd></div>
      </dl>
    </div>
  );
}
