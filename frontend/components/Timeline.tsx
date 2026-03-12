import type { RunStatus } from "@/types/api";

type StageState = "pending" | "running" | "success" | "failed";
type PipelineEvent = { stage?: string; status?: string; error?: string };

const stageDefs = [
  { key: "init_state", label: "Initialize State" },
  { key: "generate_fireworks", label: "Generate (Fireworks)" },
  { key: "validate_fireworks", label: "Validate (Fireworks)" },
  { key: "generate_groq", label: "Generate (Groq)" },
  { key: "validate_groq", label: "Validate (Groq)" },
  { key: "generate_baseten", label: "Generate (Baseten)" },
  { key: "validate_baseten", label: "Validate (Baseten)" },
  { key: "quorum_check", label: "Quorum Check" },
  { key: "consolidate", label: "Consolidate" },
  { key: "validate_consolidated", label: "Validate Consolidated" },
  { key: "pytest_gate", label: "Pytest Gate" },
  { key: "pytest_repair_once", label: "Pytest Repair (if needed)" },
  { key: "persist", label: "Persist to DB" },
];

const statusClass: Record<StageState, string> = {
  pending: "bg-slate-200 text-slate-600 border-slate-300",
  running: "bg-blue-500 text-white border-blue-600",
  success: "bg-green-500 text-white border-green-700",
  failed: "bg-red-500 text-white border-red-700",
};

function normalize(status?: string): StageState {
  if (!status) return "pending";
  if (status === "success" || status === "passed" || status === "done") return "success";
  if (status === "failed" || status === "error") return "failed";
  return "running";
}

export function Timeline({ status, events = [] }: { status: RunStatus; events?: PipelineEvent[] }) {
  const stageStatus = new Map<string, StageState>();
  let failedAt: string | null = null;

  for (const e of events) {
    if (!e?.stage) continue;
    const state = normalize(e.status);
    stageStatus.set(e.stage, state);
    if (state === "failed" && !failedAt) failedAt = e.stage;
  }

  if (status === "running") {
    const next = stageDefs.find((s) => !stageStatus.has(s.key));
    if (next) stageStatus.set(next.key, "running");
  }

  if (status === "succeeded") {
    for (const s of stageDefs) {
      if (!stageStatus.has(s.key)) stageStatus.set(s.key, "success");
    }
  }

  return (
    <div className="card">
      <h3 className="mb-2 font-semibold">Pipeline Timeline</h3>
      <ol className="space-y-3 text-sm">
        {stageDefs.map((s, i) => {
          const nodeState = stageStatus.get(s.key) ?? "pending";
          const icon = nodeState === "success" ? "✓" : nodeState === "failed" ? "✕" : nodeState === "running" ? "…" : "";
          return (
            <li key={s.key} className="relative flex items-center gap-3">
              {i < stageDefs.length - 1 && (
                <span className="absolute left-[13px] top-7 h-6 w-px bg-slate-300" />
              )}
              <span
                className={`relative z-10 inline-flex h-7 min-w-7 items-center justify-center rounded-full border text-xs font-bold shadow-sm ${statusClass[nodeState]}`}
                title={nodeState}
              >
                {icon || i + 1}
              </span>
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate">{s.label}</span>
                <span
                  className={`rounded px-2 py-0.5 text-[11px] font-medium ${
                    nodeState === "success"
                      ? "bg-green-50 text-green-700"
                      : nodeState === "failed"
                        ? "bg-red-50 text-red-700"
                        : nodeState === "running"
                          ? "bg-blue-50 text-blue-700"
                          : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {nodeState}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
      {failedAt && <p className="mt-3 text-xs text-red-700">Failed at: {failedAt}</p>}
    </div>
  );
}
