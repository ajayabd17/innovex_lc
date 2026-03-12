import type { RunStatus } from "@/types/api";

const colorMap: Record<RunStatus, string> = {
  queued: "bg-slate-200 text-slate-700",
  running: "bg-blue-100 text-blue-700",
  succeeded: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${colorMap[status]}`}>{status}</span>;
}
