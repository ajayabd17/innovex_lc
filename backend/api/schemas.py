"""API schemas for run endpoints."""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    company_name: str = Field(..., min_length=1)
    idempotency_key: Optional[str] = None


class RunEstimateRequest(BaseModel):
    company_name: str = Field(..., min_length=1)


class RunEstimateResponse(BaseModel):
    company_name: str
    field_count: int
    providers: list[str]
    min_success_models: int
    chunk_size: int
    chunks_per_provider: int
    estimated_api_calls: Dict[str, int]
    estimated_tokens: Dict[str, int]
    estimated_cost_usd: float
    estimated_duration_sec: Dict[str, float]
    live: Dict[str, int]


class RunSummaryResponse(BaseModel):
    run_id: str
    company_name: str
    status: str
    attempt: int
    parent_run_id: Optional[str] = None
    error: Optional[str] = None
    database_id: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    events: Optional[list[Dict[str, Any]]] = None


class CreateRunResponse(BaseModel):
    run_id: str
    status: str
    company_name: str
    created_at: str


class RetryRunResponse(BaseModel):
    run_id: str
    parent_run_id: str
    attempt: int
    status: str


class RunResultResponse(BaseModel):
    run_id: str
    status: str
    result: Dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    pipeline_ready: bool


class ErrorEnvelope(BaseModel):
    error: Dict[str, Any]
