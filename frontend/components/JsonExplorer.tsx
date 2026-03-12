"use client";

import { useMemo, useState } from "react";

function JsonNode({ name, value, level = 0 }: { name: string; value: unknown; level?: number }) {
  const [open, setOpen] = useState(level < 1);
  const isObject = value !== null && typeof value === "object";

  if (!isObject) {
    return (
      <div className="font-mono text-xs">
        <span className="text-slate-400">"{name}"</span>: <span className="text-cyan-300">{JSON.stringify(value)}</span>
      </div>
    );
  }

  const entries = Object.entries(value as Record<string, unknown>);
  return (
    <div className="font-mono text-xs">
      <button className="mr-2 text-slate-400" onClick={() => setOpen((v) => !v)}>{open ? "-" : "+"}</button>
      <span className="text-slate-400">"{name}"</span>
      {open && (
        <div className="ml-4 border-l border-slate-700 pl-3">
          {entries.map(([k, v]) => (
            <JsonNode key={k} name={k} value={v} level={level + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export function JsonExplorer({ data, filename }: { data: Record<string, unknown>; filename: string }) {
  const [expanded, setExpanded] = useState(false);
  const pretty = useMemo(() => JSON.stringify(data, null, 2), [data]);

  const onCopy = async () => {
    await navigator.clipboard.writeText(pretty);
  };

  const onDownload = () => {
    const blob = new Blob([pretty], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">JSON Viewer</h3>
        <div className="flex gap-2 text-xs">
          <button className="rounded border px-2 py-1" onClick={() => setExpanded((v) => !v)}>{expanded ? "Collapse" : "Expand"}</button>
          <button className="rounded border px-2 py-1" onClick={onCopy}>Copy</button>
          <button className="rounded border px-2 py-1" onClick={onDownload}>Download</button>
        </div>
      </div>
      <div className="max-h-[560px] overflow-auto rounded-md bg-slate-950 p-3 text-slate-100">
        {expanded ? (
          <pre className="font-mono text-xs">{pretty}</pre>
        ) : (
          Object.entries(data).map(([k, v]) => <JsonNode key={k} name={k} value={v} />)
        )}
      </div>
    </div>
  );
}
