"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import type { RunEstimateResponse } from "@/types/api";
import { createRun, estimateRun } from "@/lib/api";
import { ErrorCard } from "@/components/ErrorCard";
import { RunHistoryPanel } from "@/components/RunHistoryPanel";
import { PageNav } from "@/components/PageNav";
import { useRunHistoryStore } from "@/store/runHistory";

export default function HomePage() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [estimateError, setEstimateError] = useState<unknown>(null);
  const [estimate, setEstimate] = useState<RunEstimateResponse | null>(null);
  const upsertRun = useRunHistoryStore((s) => s.upsertRun);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!companyName.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const run = await createRun(companyName.trim());
      upsertRun({
        run_id: run.run_id,
        company_name: run.company_name,
        status: run.status,
        timestamp: new Date().toISOString(),
      });
      router.push(`/runs/${run.run_id}`);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const onEstimate = async () => {
    if (!companyName.trim()) return;
    setEstimating(true);
    setEstimateError(null);
    try {
      const res = await estimateRun(companyName.trim());
      setEstimate(res);
    } catch (err) {
      setEstimate(null);
      setEstimateError(err);
    } finally {
      setEstimating(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="space-y-4 lg:col-span-2">
        <PageNav
          items={[
            { href: "/", label: "Generate", active: true },
            { href: "/system/health", label: "System Health" },
          ]}
        />
        <div className="card">
          <h2 className="text-xl font-semibold">Innovex CO-DE-GEN</h2>
          <p className="text-sm text-slate-600">AI-powered company intelligence generator</p>
        </div>

        <form className="card space-y-3" onSubmit={onSubmit}>
          <label htmlFor="company" className="text-sm font-medium">Company Name</label>
          <input
            id="company"
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            placeholder="Enter company name"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            disabled={submitting || estimating}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={submitting || estimating || !companyName.trim()}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {submitting ? "Creating Run..." : "Generate Company Intelligence"}
            </button>
            <button
              type="button"
              onClick={onEstimate}
              disabled={submitting || estimating || !companyName.trim()}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 disabled:opacity-40"
            >
              {estimating ? "Estimating..." : "Estimate Time & Cost"}
            </button>
          </div>
        </form>

        <ErrorCard error={error} />
        <ErrorCard error={estimateError} />

        {estimate && (
          <div className="card space-y-3 text-sm">
            <h3 className="font-semibold">Pre-run Estimate</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <p><span className="text-slate-500">Company:</span> {estimate.company_name}</p>
              <p><span className="text-slate-500">Fields:</span> {estimate.field_count}</p>
              <p><span className="text-slate-500">Providers:</span> {estimate.providers.join(", ")}</p>
              <p><span className="text-slate-500">API Calls:</span> {estimate.estimated_api_calls.total}</p>
              <p><span className="text-slate-500">Tokens:</span> {estimate.estimated_tokens.total.toLocaleString()}</p>
              <p><span className="text-slate-500">Cost (USD):</span> {estimate.estimated_cost_usd}</p>
              <p><span className="text-slate-500">ETA Min:</span> {estimate.estimated_duration_sec.min}s</p>
              <p><span className="text-slate-500">ETA Expected:</span> {estimate.estimated_duration_sec.expected}s</p>
              <p><span className="text-slate-500">ETA Max:</span> {estimate.estimated_duration_sec.max}s</p>
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-semibold uppercase text-slate-600">Live Queue Snapshot</p>
              <div className="mt-2 grid gap-2 sm:grid-cols-4">
                <p><span className="text-slate-500">Running:</span> {estimate.live.running_runs}</p>
                <p><span className="text-slate-500">Queued:</span> {estimate.live.queued_runs}</p>
                <p><span className="text-slate-500">Active Tasks:</span> {estimate.live.active_tasks}</p>
                <p><span className="text-slate-500">Concurrency:</span> {estimate.live.max_concurrent_runs}</p>
              </div>
            </div>
          </div>
        )}
      </section>

      <aside>
        <RunHistoryPanel />
      </aside>
    </div>
  );
}

