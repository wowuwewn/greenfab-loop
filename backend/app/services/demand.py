"""PostgreSQL Demand catalog and vector-index projections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import Demand, DemandIndexEvent
from app.schemas import DemandCreate, DemandUpdate
from app.services.match import DemandIndexDocument, DemandSnapshot
from app.services.rules import DemandRules


def list_demands(
    session: Session,
    *,
    include_inactive: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Demand], int]:
    statement = select(Demand)
    count_statement = select(func.count()).select_from(Demand)
    if not include_inactive:
        statement = statement.where(Demand.is_active.is_(True))
        count_statement = count_statement.where(Demand.is_active.is_(True))
    total = session.scalar(count_statement) or 0
    records = session.scalars(
        statement.order_by(Demand.demand_id.asc()).limit(limit).offset(offset)
    ).all()
    return list(records), total


def get_demand(session: Session, demand_id: str) -> Demand:
    demand = session.get(Demand, demand_id)
    if demand is None:
        raise DomainError("DEMAND_NOT_FOUND", f"Demand {demand_id}를 찾을 수 없습니다.", 404)
    return demand


def get_demand_for_update(session: Session, demand_id: str) -> Demand:
    demand = session.scalar(select(Demand).where(Demand.demand_id == demand_id).with_for_update())
    if demand is None:
        raise DomainError("DEMAND_NOT_FOUND", f"Demand {demand_id}를 찾을 수 없습니다.", 404)
    return demand


def create_demand(session: Session, payload: DemandCreate) -> Demand:
    if session.get(Demand, payload.demand_id) is not None:
        raise DomainError("DEMAND_ALREADY_EXISTS", "같은 demand_id가 이미 존재합니다.", 409)
    demand = Demand(**payload.model_dump(), is_active=True, version=1)
    demand.content_sha256 = demand_content_sha256(demand)
    try:
        with session.begin_nested():
            session.add(demand)
            session.flush()
    except IntegrityError as exc:
        raise DomainError(
            "DEMAND_ALREADY_EXISTS", "같은 demand_id가 이미 존재합니다.", 409
        ) from exc
    return demand


def update_demand(session: Session, demand_id: str, payload: DemandUpdate) -> tuple[Demand, bool]:
    demand = get_demand_for_update(session, demand_id)
    values = payload.model_dump()
    changed = not demand.is_active or any(
        getattr(demand, field_name) != value for field_name, value in values.items()
    )
    if not changed:
        return demand, False
    for field_name, value in values.items():
        setattr(demand, field_name, value)
    demand.is_active = True
    demand.version += 1
    demand.content_sha256 = demand_content_sha256(demand)
    session.flush()
    return demand, True


def deactivate_demand(session: Session, demand_id: str) -> tuple[Demand, bool]:
    demand = get_demand_for_update(session, demand_id)
    if not demand.is_active:
        return demand, False
    demand.is_active = False
    demand.version += 1
    demand.content_sha256 = demand_content_sha256(demand)
    session.flush()
    return demand, True


def demand_to_snapshot(demand: Demand) -> DemandSnapshot:
    return DemandSnapshot(
        demand_id=demand.demand_id,
        company_name=demand.company_name,
        demand_description=demand.demand_description,
        semantic_similarity=0.0,
        rules=DemandRules(
            quantity_min=_number(demand.quantity_min),
            quantity_max=_number(demand.quantity_max),
            unit=demand.unit,
            accepted_locations=(demand.location,) if demand.location else (),
            required_fields=tuple(demand.required_fields),
        ),
        source_type=demand.source_type.value,
        version=demand.version,
        content_sha256=demand.content_sha256 or demand_content_sha256(demand),
    )


def demand_to_index_document(demand: Demand) -> DemandIndexDocument:
    parts = [
        demand.company_name,
        demand.demand_description,
        demand.location,
        " ".join(demand.accepted_conditions),
    ]
    searchable_text = "\n".join(part.strip() for part in parts if part and part.strip())
    return DemandIndexDocument(
        demand_id=demand.demand_id,
        searchable_text=searchable_text,
        version=demand.version,
        content_sha256=demand.content_sha256 or demand_content_sha256(demand),
    )


class SqlAlchemyDemandCatalog:
    """Hydrate every rule and response field from active PostgreSQL rows."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def load_active(self, demand_ids: Sequence[str]) -> dict[str, DemandSnapshot]:
        if not demand_ids:
            return {}
        with self._session_factory() as session:
            records = session.scalars(
                select(Demand).where(
                    Demand.demand_id.in_(set(demand_ids)),
                    Demand.is_active.is_(True),
                )
            ).all()
            return {record.demand_id: demand_to_snapshot(record) for record in records}

    def list_active_documents(self) -> list[DemandIndexDocument]:
        with self._session_factory() as session:
            records = session.scalars(
                select(Demand).where(Demand.is_active.is_(True)).order_by(Demand.demand_id.asc())
            ).all()
            return [demand_to_index_document(record) for record in records]

    def load_active_document(self, demand_id: str) -> DemandIndexDocument | None:
        with self._session_factory() as session:
            record = session.get(Demand, demand_id)
            if record is None or not record.is_active:
                return None
            return demand_to_index_document(record)


def _number(value: object | None) -> float | None:
    return float(value) if value is not None else None


def demand_content_sha256(demand: Demand) -> str:
    """Hash the relational Demand fields that affect matching or display."""

    canonical = json.dumps(
        demand_snapshot_payload(demand),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def demand_snapshot_payload(demand: Demand) -> dict[str, Any]:
    return {
        "demand_id": demand.demand_id,
        "company_name": demand.company_name,
        "demand_description": demand.demand_description,
        "quantity_min": _number(demand.quantity_min),
        "quantity_max": _number(demand.quantity_max),
        "unit": demand.unit,
        "location": demand.location,
        "accepted_conditions": list(demand.accepted_conditions),
        "required_fields": list(demand.required_fields),
        "source_type": demand.source_type.value,
        "is_active": demand.is_active,
        "version": demand.version,
    }


IndexOperation = Literal["UPSERT", "DELETE", "SYNC_ALL"]


def create_index_event(
    session: Session,
    *,
    operation: IndexOperation,
    requested_by: str,
    demand_id: str | None = None,
    target_version: int | None = None,
    target_content_sha256: str | None = None,
    trace_id: str | None = None,
) -> DemandIndexEvent:
    event = DemandIndexEvent(
        demand_id=demand_id,
        operation=operation,
        status="PENDING",
        requested_by=requested_by,
        target_version=target_version,
        target_content_sha256=target_content_sha256,
        trace_id=trace_id,
    )
    session.add(event)
    session.flush()
    return event


def complete_index_event(
    session: Session,
    event_id: str,
    *,
    status: Literal["SUCCEEDED", "FAILED", "SKIPPED"],
    error_message: str | None = None,
) -> DemandIndexEvent:
    event = session.get(DemandIndexEvent, event_id)
    if event is None:
        raise RuntimeError(f"Demand index event {event_id} is missing")
    event.status = status
    event.attempt_count += 1
    event.error_message = error_message
    event.processed_at = datetime.now(UTC)
    session.flush()
    return event


def list_index_events(session: Session, *, limit: int = 100) -> list[DemandIndexEvent]:
    return list(
        session.scalars(
            select(DemandIndexEvent)
            .order_by(DemandIndexEvent.created_at.desc(), DemandIndexEvent.event_id.desc())
            .limit(limit)
        ).all()
    )


def get_index_event_for_retry(session: Session, event_id: str) -> DemandIndexEvent:
    event = session.scalar(
        select(DemandIndexEvent).where(DemandIndexEvent.event_id == event_id).with_for_update()
    )
    if event is None:
        raise DomainError(
            "DEMAND_INDEX_EVENT_NOT_FOUND",
            "Demand index event를 찾을 수 없습니다.",
            404,
        )
    if event.status == "SUCCEEDED":
        raise DomainError(
            "DEMAND_INDEX_EVENT_ALREADY_SUCCEEDED",
            "성공한 Demand index event는 재시도할 수 없습니다.",
            409,
        )
    if event.status == "PENDING":
        raise DomainError(
            "DEMAND_INDEX_EVENT_IN_PROGRESS",
            "진행 중인 Demand index event는 재시도할 수 없습니다. 전체 동기화를 사용해 주세요.",
            409,
        )
    return event


def create_index_event_retry(
    session: Session,
    event_id: str,
    *,
    requested_by: str,
    trace_id: str | None = None,
) -> DemandIndexEvent:
    """Supersede a recoverable event with an auditable new attempt."""

    previous = get_index_event_for_retry(session, event_id)
    target_version = previous.target_version
    target_content_sha256 = previous.target_content_sha256
    operation: IndexOperation = previous.operation
    if previous.demand_id is not None:
        demand = session.get(Demand, previous.demand_id)
        if demand is not None:
            operation = "UPSERT" if demand.is_active else "DELETE"
            target_version = demand.version
            target_content_sha256 = demand.content_sha256 or demand_content_sha256(demand)
    return create_index_event(
        session,
        operation=operation,
        requested_by=requested_by,
        demand_id=previous.demand_id,
        target_version=target_version,
        target_content_sha256=target_content_sha256,
        trace_id=trace_id,
    )
