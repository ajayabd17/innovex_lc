"""FastAPI wrapper for Innovex LangGraph pipeline."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes.health import router as health_router
from api.routes.runs import router as runs_router
from services.run_orchestrator import RunOrchestrator
from storage.run_store import RunStore

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Innovex Pipeline API", version="1.0.0")
    cors_origins_raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    run_store_path = os.getenv("RUN_STORE_JSONL_PATH", "output/pipeline_runs.jsonl")
    run_store_limit = int(os.getenv("RUN_STORE_MEMORY_LIMIT", "2000"))
    max_concurrent = int(os.getenv("MAX_CONCURRENT_RUNS", "2"))

    app.state.run_store = RunStore(run_store_path, memory_limit=run_store_limit)
    app.state.orchestrator = RunOrchestrator(app.state.run_store, max_concurrent_runs=max_concurrent)

    app.include_router(health_router)
    app.include_router(runs_router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            return JSONResponse(status_code=exc.status_code, content={"error": detail})
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(detail), "details": {}}},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception):
        logger.exception("Unhandled API error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": str(exc), "details": {}}},
        )

    return app


app = create_app()
