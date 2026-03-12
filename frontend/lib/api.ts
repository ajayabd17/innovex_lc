import {
  CreateRunResponseSchema,
  ErrorEnvelopeSchema,
  HealthResponseSchema,
  RunEstimateResponseSchema,
  RetryRunResponseSchema,
  RunResultResponseSchema,
  RunStatusResponseSchema,
} from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  status: number;

  constructor(message: string, code = "UNKNOWN_ERROR", status = 500, details: Record<string, unknown> = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function parseResponse<T>(res: Response, schema: { parse: (d: unknown) => T }): Promise<T> {
  const payload = await res.json().catch(() => ({}));

  if (!res.ok) {
    const parsed = ErrorEnvelopeSchema.safeParse(payload);
    if (parsed.success) {
      throw new ApiError(parsed.data.error.message, parsed.data.error.code, res.status, parsed.data.error.details || {});
    }
    throw new ApiError(`HTTP ${res.status}`, "HTTP_ERROR", res.status, { raw: payload });
  }

  return schema.parse(payload);
}

export async function createRun(companyName: string, idempotencyKey?: string) {
  const res = await fetch(`${API_BASE}/v1/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_name: companyName, idempotency_key: idempotencyKey }),
  });
  return parseResponse(res, CreateRunResponseSchema);
}

export async function estimateRun(companyName: string) {
  const res = await fetch(`${API_BASE}/v1/runs/estimate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_name: companyName }),
  });
  return parseResponse(res, RunEstimateResponseSchema);
}

export async function getRunStatus(runId: string) {
  const res = await fetch(`${API_BASE}/v1/runs/${runId}`, { cache: "no-store" });
  return parseResponse(res, RunStatusResponseSchema);
}

export async function getRunResult(runId: string) {
  const res = await fetch(`${API_BASE}/v1/runs/${runId}/result`, { cache: "no-store" });
  return parseResponse(res, RunResultResponseSchema);
}

export async function downloadRunCsv(runId: string) {
  const res = await fetch(`${API_BASE}/v1/runs/${runId}/download/csv`, { cache: "no-store" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    const parsed = ErrorEnvelopeSchema.safeParse(payload);
    if (parsed.success) {
      throw new ApiError(parsed.data.error.message, parsed.data.error.code, res.status, parsed.data.error.details || {});
    }
    throw new ApiError(`HTTP ${res.status}`, "HTTP_ERROR", res.status, { raw: payload });
  }

  const blob = await res.blob();
  const contentDisposition = res.headers.get("content-disposition") || "";
  const filenameMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
  const filename = filenameMatch?.[1] || `company_detail_${runId}.csv`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function retryRun(runId: string) {
  const res = await fetch(`${API_BASE}/v1/runs/${runId}/retry`, { method: "POST" });
  return parseResponse(res, RetryRunResponseSchema);
}

export async function getHealth() {
  const t0 = performance.now();
  const res = await fetch(`${API_BASE}/v1/health`, { cache: "no-store" });
  const data = await parseResponse(res, HealthResponseSchema);
  const latencyMs = Math.round(performance.now() - t0);
  return { ...data, latencyMs };
}
