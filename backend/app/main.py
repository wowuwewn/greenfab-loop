from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router, health_router
from app.config import settings
from app.database import SessionLocal
from app.errors import register_exception_handlers
from app.seed import seed_demo_data
from app.services.match import DemandIndexManager, MatchProvider
from app.services.runtime_match import build_match_provider
from app.storage import EvidenceStorage, LocalEvidenceStorage


def create_app(
    *,
    match_provider: MatchProvider | None = None,
    evidence_storage: EvidenceStorage | None = None,
    seed_on_startup: bool | None = None,
) -> FastAPI:
    should_seed = settings.seed_demo_data if seed_on_startup is None else seed_on_startup
    configured_provider = match_provider or build_match_provider(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if should_seed:
            with SessionLocal.begin() as session:
                seed_demo_data(session)
        if settings.demand_index_sync_on_startup and isinstance(
            configured_provider, DemandIndexManager
        ):
            configured_provider.sync_all_demands()
        configured_provider.ready()
        yield

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=("GreenFab Loop의 상태 전이와 Data Contract v0.1을 제공하는 MVP API"),
        lifespan=lifespan,
    )
    application.state.match_provider = configured_provider
    application.state.evidence_storage = evidence_storage or LocalEvidenceStorage(
        settings.evidence_storage_root
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-Id", "X-Total-Count", "X-Limit", "X-Offset"],
    )

    @application.middleware("http")
    async def attach_trace_id(request: Request, call_next):
        supplied_trace_id = (request.headers.get("X-Trace-Id") or "").strip()
        trace_id = supplied_trace_id if 1 <= len(supplied_trace_id) <= 64 else str(uuid4())
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()
