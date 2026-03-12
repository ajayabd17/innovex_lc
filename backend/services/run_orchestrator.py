"""Background run orchestration for FastAPI service."""
from __future__ import annotations

import asyncio
import math
import os
from dataclasses import asdict
from typing import Optional

from services.pipeline_service import PipelineService
from storage.run_store import RunRecord, RunStore


class RunOrchestrator:
    def __init__(self, run_store: RunStore, max_concurrent_runs: int = 2):
        self.run_store = run_store
        self.pipeline_service = PipelineService()
        self.max_concurrent_runs = max(1, int(max_concurrent_runs))
        self.semaphore = asyncio.Semaphore(self.max_concurrent_runs)
        self.tasks: dict[str, asyncio.Task] = {}

    async def submit_run(self, company_name: str, idempotency_key: Optional[str] = None) -> RunRecord:
        if idempotency_key:
            existing = self.run_store.find_by_idempotency(company_name, idempotency_key)
            if existing:
                return existing

        record = self.run_store.create_run(company_name=company_name, idempotency_key=idempotency_key)
        task = asyncio.create_task(self._execute(record.run_id))
        self.tasks[record.run_id] = task
        return record

    async def retry_run(self, run_id: str) -> Optional[RunRecord]:
        parent = self.run_store.get_run(run_id)
        if not parent:
            return None
        attempt = int(parent.attempt) + 1
        record = self.run_store.create_run(
            company_name=parent.company_name,
            attempt=attempt,
            parent_run_id=parent.run_id,
        )
        task = asyncio.create_task(self._execute(record.run_id))
        self.tasks[record.run_id] = task
        return record

    async def _execute(self, run_id: str) -> None:
        async with self.semaphore:
            running = self.run_store.mark_running(run_id)
            if not running:
                return
            try:
                result = await self.pipeline_service.run(
                    running.company_name,
                    progress_callback=lambda event: self.run_store.mark_progress(run_id, event),
                )
                self.run_store.mark_succeeded(
                    run_id=run_id,
                    result=result,
                    database_id=result.get("database_id"),
                    events=result.get("events", []),
                )
            except Exception as exc:
                self.run_store.mark_failed(
                    run_id=run_id,
                    error=str(exc),
                    events=[{"stage": "api_orchestrator", "status": "failed", "error": str(exc)}],
                )
            finally:
                self.tasks.pop(run_id, None)

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        return self.run_store.get_run(run_id)

    def serialize_record(self, record: RunRecord) -> dict:
        return asdict(record)

    def estimate_run(self, company_name: str) -> dict:
        pipeline = self.pipeline_service.pipeline
        field_count = len(pipeline.schema_loader.get_all_field_names())
        providers = list(pipeline.generator.providers)
        chunk_size = max(1, int(pipeline.generator.chunk_size))
        chunks_per_provider = math.ceil(field_count / chunk_size)

        generation_calls = len(providers) * chunks_per_provider
        consolidation_calls = 1 if int(pipeline.generator.min_success_models) >= 2 else 0
        total_calls = generation_calls + consolidation_calls

        # Rough provider timings (seconds/call) tuned from observed runtime behavior.
        sec_per_call = {
            "groq": float(os.getenv("ESTIMATE_SEC_PER_CALL_GROQ", "1.2")),
            "fireworks": float(os.getenv("ESTIMATE_SEC_PER_CALL_FIREWORKS", "4.5")),
            "baseten": float(os.getenv("ESTIMATE_SEC_PER_CALL_BASETEN", "6.0")),
        }
        sec_per_consolidation = float(os.getenv("ESTIMATE_SEC_CONSOLIDATION", "4.0"))
        base_overhead = float(os.getenv("ESTIMATE_BASE_OVERHEAD_SEC", "6.0"))

        generation_sec = sum(sec_per_call.get(p, 3.0) * chunks_per_provider for p in providers)
        single_run_estimate = generation_sec + (sec_per_consolidation * consolidation_calls) + base_overhead
        single_run_min = max(10.0, single_run_estimate * 0.75)
        single_run_max = single_run_estimate * 1.60

        # Live queue should come from current process tasks to avoid stale persisted run-state.
        active_tasks = sum(1 for task in self.tasks.values() if not task.done())
        running = min(active_tasks, self.max_concurrent_runs)
        queued = max(0, active_tasks - running)
        queue_wait_sec = queued * (single_run_estimate / max(1, self.max_concurrent_runs))

        # Coarse token/cost estimate.
        input_tokens_per_call = int(os.getenv("ESTIMATE_INPUT_TOKENS_PER_CALL", "3500"))
        output_tokens_per_call = int(os.getenv("ESTIMATE_OUTPUT_TOKENS_PER_CALL", "900"))
        est_input_tokens = total_calls * input_tokens_per_call
        est_output_tokens = total_calls * output_tokens_per_call

        # Optional pricing env vars (per 1M tokens). Defaults to 0 when unknown.
        in_rate = float(os.getenv("ESTIMATE_COST_PER_1M_INPUT_USD", "0"))
        out_rate = float(os.getenv("ESTIMATE_COST_PER_1M_OUTPUT_USD", "0"))
        estimated_cost_usd = round((est_input_tokens / 1_000_000) * in_rate + (est_output_tokens / 1_000_000) * out_rate, 6)

        return {
            "company_name": company_name,
            "field_count": field_count,
            "providers": providers,
            "min_success_models": int(pipeline.generator.min_success_models),
            "chunk_size": chunk_size,
            "chunks_per_provider": chunks_per_provider,
            "estimated_api_calls": {
                "generation": generation_calls,
                "consolidation": consolidation_calls,
                "total": total_calls,
            },
            "estimated_tokens": {
                "input": est_input_tokens,
                "output": est_output_tokens,
                "total": est_input_tokens + est_output_tokens,
            },
            "estimated_cost_usd": estimated_cost_usd,
            "estimated_duration_sec": {
                "min": round(single_run_min + queue_wait_sec, 1),
                "expected": round(single_run_estimate + queue_wait_sec, 1),
                "max": round(single_run_max + queue_wait_sec, 1),
                "queue_wait": round(queue_wait_sec, 1),
            },
            "live": {
                "running_runs": running,
                "queued_runs": queued,
                "max_concurrent_runs": self.max_concurrent_runs,
                "active_tasks": active_tasks,
            },
        }
