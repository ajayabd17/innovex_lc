"""Health endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request

from api.schemas import HealthResponse

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    pipeline_ready = bool(getattr(request.app.state, "orchestrator", None))
    return HealthResponse(status="ok", pipeline_ready=pipeline_ready)

