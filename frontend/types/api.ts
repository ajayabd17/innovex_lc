import { z } from "zod";

export const RunStatusEnum = z.enum(["queued", "running", "succeeded", "failed"]);

export const ErrorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.any()).optional().default({}),
  }),
});

export const CreateRunResponseSchema = z.object({
  run_id: z.string(),
  status: RunStatusEnum,
  company_name: z.string(),
  created_at: z.string(),
});

export const RunStatusResponseSchema = z.object({
  run_id: z.string(),
  company_name: z.string(),
  status: RunStatusEnum,
  attempt: z.number(),
  parent_run_id: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  database_id: z.string().nullable().optional(),
  created_at: z.string(),
  started_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  events: z.array(
    z.object({
      stage: z.string(),
      status: z.string().optional(),
      error: z.string().optional(),
      provider: z.string().optional(),
    }).passthrough(),
  ).optional().default([]),
});

export const RunResultResponseSchema = z.object({
  run_id: z.string(),
  status: z.literal("succeeded"),
  result: z.record(z.any()),
});

export const RetryRunResponseSchema = z.object({
  run_id: z.string(),
  parent_run_id: z.string(),
  attempt: z.number(),
  status: z.string(),
});

export const HealthResponseSchema = z.object({
  status: z.string(),
  pipeline_ready: z.boolean(),
});

export const RunEstimateResponseSchema = z.object({
  company_name: z.string(),
  field_count: z.number(),
  providers: z.array(z.string()),
  min_success_models: z.number(),
  chunk_size: z.number(),
  chunks_per_provider: z.number(),
  estimated_api_calls: z.object({
    generation: z.number(),
    consolidation: z.number(),
    total: z.number(),
  }),
  estimated_tokens: z.object({
    input: z.number(),
    output: z.number(),
    total: z.number(),
  }),
  estimated_cost_usd: z.number(),
  estimated_duration_sec: z.object({
    min: z.number(),
    expected: z.number(),
    max: z.number(),
    queue_wait: z.number(),
  }),
  live: z.object({
    running_runs: z.number(),
    queued_runs: z.number(),
    max_concurrent_runs: z.number(),
    active_tasks: z.number(),
  }),
});

export type RunStatus = z.infer<typeof RunStatusEnum>;
export type CreateRunResponse = z.infer<typeof CreateRunResponseSchema>;
export type RunStatusResponse = z.infer<typeof RunStatusResponseSchema>;
export type RunResultResponse = z.infer<typeof RunResultResponseSchema>;
export type RetryRunResponse = z.infer<typeof RetryRunResponseSchema>;
export type HealthResponse = z.infer<typeof HealthResponseSchema>;
export type RunEstimateResponse = z.infer<typeof RunEstimateResponseSchema>;
