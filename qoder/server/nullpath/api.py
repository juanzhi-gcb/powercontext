from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pymysql
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .comparator import build_comparator
from .config import Settings
from .context import PowerContextAdapter, PowerContextUnavailable
from .embeddings import build_embedder
from .models import (
    ArchiveImport,
    AttemptCreate,
    DecisionCreate,
    EvaluationRunCreate,
    ExperimentCreate,
    HistorySearchCreate,
    ReplayCreate,
    ResearchSourceImport,
    SecretaryReviewCreate,
)
from .service import CutoffViolationError, ResearchService
from .store import SeekDBStore


def create_app(
    *,
    store: Any | None = None,
    context: Any | None = None,
    embedder: Any | None = None,
    comparator: Any | None = None,
) -> FastAPI:
    settings = Settings.from_env()
    store = store or SeekDBStore(settings)
    context = context or PowerContextAdapter(settings)
    service = ResearchService(
        store,
        embedder or build_embedder(),
        comparator or build_comparator(),
        context,
    )
    app = FastAPI(
        title="NullPath Research CI",
        version="0.1.0",
        description="Evidence-backed regression checks for research decisions",
    )
    app.state.service = service
    app.state.store = store
    app.state.context = context
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(KeyError)
    async def not_found(_: Request, error: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error.args[0])})

    @app.exception_handler(CutoffViolationError)
    async def cutoff_violation(_: Request, error: CutoffViolationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(PowerContextUnavailable)
    async def context_unavailable(_: Request, error: PowerContextUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "PowerContext is required to persist secretary proposals",
                "error": str(error),
            },
        )

    @app.exception_handler(pymysql.MySQLError)
    async def database_unavailable(_: Request, error: pymysql.MySQLError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "seekdb request failed", "error": str(error)},
        )

    @app.get("/api")
    async def root() -> dict[str, Any]:
        return {
            "name": "NullPath Research CI",
            "version": "0.1.0",
            "decision_policy": "machine recommendation and human final decision are separate",
        }

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        try:
            database = await asyncio.to_thread(store.health)
        except (pymysql.MySQLError, OSError) as error:
            database = {"status": "unavailable", "error": str(error)}
        return {
            "seekdb": database,
            "powercontext": await asyncio.to_thread(context.status),
        }

    @app.post("/api/history-search")
    async def search_history(search: HistorySearchCreate) -> dict[str, Any]:
        return await asyncio.to_thread(service.search_history, search.query)

    @app.post("/api/attempts", status_code=201)
    async def create_attempt(attempt: AttemptCreate) -> dict[str, Any]:
        created = await asyncio.to_thread(service.create_attempt, attempt)
        context_warning = None
        if context.configured:
            contract = json.dumps(
                {
                    "attempt_id": created["id"],
                    "goal": attempt.idea,
                    "resources": {
                        "gpu_count": attempt.gpu_count,
                        "pilot_hours": attempt.pilot_hours,
                        "storage_gb": attempt.storage_gb,
                    },
                    "stage": "precheck",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            try:
                await asyncio.to_thread(context.save_state, "active_research_contract", contract)
            except PowerContextUnavailable as error:
                context_warning = str(error)
        return {**created, "context_warning": context_warning}

    @app.get("/api/attempts")
    async def list_attempts() -> list[dict[str, Any]]:
        return await asyncio.to_thread(store.list_attempts)

    @app.post("/api/imports/archive", status_code=201)
    async def import_archive(archive: ArchiveImport) -> dict[str, Any]:
        imported = await asyncio.to_thread(service.import_archive, archive)
        return {"imported": len(imported), "attempts": imported}

    @app.post("/api/imports/sources", status_code=201)
    async def import_sources(sources: ResearchSourceImport) -> dict[str, Any]:
        return await asyncio.to_thread(service.import_sources, sources)

    @app.get("/api/sources")
    async def list_sources() -> list[dict[str, Any]]:
        return await asyncio.to_thread(store.list_sources)

    @app.post("/api/secretary/runs", status_code=201)
    async def run_secretary() -> dict[str, Any]:
        return await asyncio.to_thread(service.run_secretary)

    @app.get("/api/secretary")
    async def get_secretary() -> dict[str, Any]:
        return await asyncio.to_thread(service.get_secretary)

    @app.post("/api/secretary/reviews")
    async def review_secretary(review: SecretaryReviewCreate) -> dict[str, Any]:
        return await asyncio.to_thread(service.review_secretary, review)

    @app.post("/api/evaluation-runs", status_code=201)
    async def create_evaluation(request: EvaluationRunCreate) -> dict[str, Any]:
        return await asyncio.to_thread(service.run_evaluation, request)

    @app.get("/api/evaluation-runs")
    async def list_evaluations() -> list[dict[str, Any]]:
        return await asyncio.to_thread(store.list_runs)

    @app.get("/api/evaluation-runs/{run_id}")
    async def get_evaluation(run_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(store.get_run, run_id)

    @app.get("/api/attempts/{attempt_id}/lineage")
    async def get_lineage(attempt_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(store.lineage, attempt_id)

    @app.post("/api/decisions", status_code=201)
    async def save_decision(decision: DecisionCreate) -> dict[str, Any]:
        saved = await asyncio.to_thread(store.add_decision, decision)
        context_warning = None
        if context.configured:
            try:
                run = await asyncio.to_thread(store.get_run, decision.run_id)
                await asyncio.to_thread(
                    context.save_pointer,
                    run["attempt_id"],
                    decision.run_id,
                    decision.decision.value,
                )
                await asyncio.to_thread(
                    context.save_handoff,
                    f"Human decision saved for run {decision.run_id}",
                    decision.restart_conditions or "No unresolved restart condition declared",
                    "Run the minimum experiment or create a revised precheck",
                )
            except PowerContextUnavailable as error:
                context_warning = str(error)
        return {**saved, "context_warning": context_warning}

    @app.post("/api/experiments", status_code=201)
    async def save_experiment(experiment: ExperimentCreate) -> dict[str, Any]:
        return await asyncio.to_thread(store.add_experiment, experiment)

    @app.post("/api/replays", status_code=201)
    async def replay(replay: ReplayCreate) -> dict[str, Any]:
        return await asyncio.to_thread(service.replay, replay)

    @app.get("/api/context")
    async def context_status() -> dict[str, Any]:
        return await asyncio.to_thread(context.status)

    return app


app = create_app()
