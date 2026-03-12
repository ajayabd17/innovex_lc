"""Run lifecycle endpoints."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    RunEstimateRequest,
    RunEstimateResponse,
    RetryRunResponse,
    RunResultResponse,
    RunSummaryResponse,
)

router = APIRouter(prefix="/v1/runs", tags=["runs"])


def _serialize_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


@router.post("", response_model=CreateRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_run(payload: CreateRunRequest, request: Request):
    orchestrator = request.app.state.orchestrator
    record = await orchestrator.submit_run(payload.company_name.strip(), payload.idempotency_key)
    return CreateRunResponse(
        run_id=record.run_id,
        status=record.status,
        company_name=record.company_name,
        created_at=record.created_at,
    )


@router.post("/estimate", response_model=RunEstimateResponse)
async def estimate_run(payload: RunEstimateRequest, request: Request):
    orchestrator = request.app.state.orchestrator
    return orchestrator.estimate_run(payload.company_name.strip())


@router.get("/{run_id}", response_model=RunSummaryResponse)
async def get_run_status(run_id: str, request: Request):
    orchestrator = request.app.state.orchestrator
    record = orchestrator.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"Run '{run_id}' not found"})
    return RunSummaryResponse(
        run_id=record.run_id,
        company_name=record.company_name,
        status=record.status,
        attempt=record.attempt,
        parent_run_id=record.parent_run_id,
        error=record.error,
        database_id=record.database_id,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        events=record.events or [],
    )


@router.get("/{run_id}/result", response_model=RunResultResponse)
async def get_run_result(run_id: str, request: Request):
    orchestrator = request.app.state.orchestrator
    record = orchestrator.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"Run '{run_id}' not found"})
    if record.status in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail={"code": "RUN_NOT_READY", "message": f"Run '{run_id}' is still {record.status}"},
        )
    if record.status == "failed":
        raise HTTPException(
            status_code=422,
            detail={"code": "PIPELINE_FAILED", "message": record.error or "Pipeline execution failed"},
        )
    if not record.result:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Run is succeeded but result payload is missing"},
        )
    return RunResultResponse(run_id=record.run_id, status=record.status, result=record.result)


@router.post("/{run_id}/retry", response_model=RetryRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_run(run_id: str, request: Request):
    orchestrator = request.app.state.orchestrator
    record = await orchestrator.retry_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"Run '{run_id}' not found"})
    return RetryRunResponse(
        run_id=record.run_id,
        parent_run_id=record.parent_run_id or run_id,
        attempt=record.attempt,
        status=record.status,
    )


@router.get("/{run_id}/download/csv")
async def download_run_csv(run_id: str, request: Request):
    orchestrator = request.app.state.orchestrator
    record = orchestrator.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": f"Run '{run_id}' not found"})
    if record.status in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail={"code": "RUN_NOT_READY", "message": f"Run '{run_id}' is still {record.status}"},
        )
    if record.status == "failed":
        raise HTTPException(
            status_code=422,
            detail={"code": "PIPELINE_FAILED", "message": record.error or "Pipeline execution failed"},
        )
    if not record.result:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Run is succeeded but result payload is missing"},
        )

    result = record.result
    payload = result.get("company_json", result)
    if not isinstance(payload, dict):
        payload = {"value": payload}

    ordered_data = {
        "_run_id": record.run_id,
        "_company_name": record.company_name,
        "_status": record.status,
        "_attempt": record.attempt,
        "_database_id": record.database_id or "",
        "_confidence": _serialize_csv_value(result.get("confidence")),
        "_created_at": record.created_at,
        "_completed_at": record.completed_at or "",
    }
    for key, value in payload.items():
        ordered_data[key] = _serialize_csv_value(value)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    # Vertical key-value view (two columns) for spreadsheet readability.
    for key, value in ordered_data.items():
        writer.writerow([key, value])

    filename = f"company_detail_{run_id}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
