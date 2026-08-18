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
from app.services.demand import complete_index_event, create_index_event
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
        sync_event_id: str | None = None
        if should_seed or (
            settings.demand_index_sync_on_startup
            and isinstance(configured_provider, DemandIndexManager)
        ):
            with SessionLocal.begin() as session:
                if should_seed:
                    seed_demo_data(session)
                if settings.demand_index_sync_on_startup and isinstance(
                    configured_provider, DemandIndexManager
                ):
                    sync_event_id = create_index_event(
                        session,
                        operation="SYNC_ALL",
                        requested_by="system",
                    ).event_id
        if settings.demand_index_sync_on_startup and isinstance(
            configured_provider, DemandIndexManager
        ):
            try:
                configured_provider.sync_all_demands()
            except Exception as exc:
                if sync_event_id is not None:
                    with SessionLocal.begin() as session:
                        complete_index_event(
                            session,
                            sync_event_id,
                            status="FAILED",
                            error_message=type(exc).__name__,
                        )
                raise
            else:
                if sync_event_id is not None:
                    with SessionLocal.begin() as session:
                        complete_index_event(session, sync_event_id, status="SUCCEEDED")
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
