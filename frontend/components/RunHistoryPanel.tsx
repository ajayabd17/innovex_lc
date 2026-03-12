"use client";

import Link from "next/link";
import { useRunHistoryStore } from "@/store/runHistory";

export function RunHistoryPanel() {
  const { runs, removeRun } = useRunHistoryStore();

  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">Recent Runs</h3>
      </div>
      {runs.length === 0 ? (
        <p className="text-sm text-slate-500">No recent runs.</p>
      ) : (
        <ul className="space-y-2">
          {runs.map((r) => (
            <li key={r.run_id} className="rounded-md border border-slate-200 p-2 text-sm">
              <div className="flex items-center justify-between">
                <Link className="font-mono text-xs text-blue-700" href={`/runs/${r.run_id}`}>{r.run_id}</Link>
                <button className="text-xs text-slate-500 hover:text-red-600" onClick={() => removeRun(r.run_id)}>Delete</button>
              </div>
              <p className="truncate">{r.company_name}</p>
              <p className="text-xs text-slate-500">{r.status} · {new Date(r.timestamp).toLocaleString()}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
