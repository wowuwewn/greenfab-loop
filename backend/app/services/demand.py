"""PostgreSQL Demand catalog and vector-index projections."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import Demand
from app.schemas import DemandCreate, DemandUpdate
from app.services.match import DemandIndexDocument, DemandSnapshot
from app.services.rules import DemandRules


def list_demands(session: Session, *, include_inactive: bool = False) -> list[Demand]:
    statement = select(Demand)
    if not include_inactive:
        statement = statement.where(Demand.is_active.is_(True))
    return list(session.scalars(statement.order_by(Demand.demand_id.asc())).all())


def get_demand(session: Session, demand_id: str) -> Demand:
    demand = session.get(Demand, demand_id)
    if demand is None:
        raise DomainError("DEMAND_NOT_FOUND", f"Demand {demand_id}를 찾을 수 없습니다.", 404)
    return demand


def create_demand(session: Session, payload: DemandCreate) -> Demand:
    if session.get(Demand, payload.demand_id) is not None:
        raise DomainError("DEMAND_ALREADY_EXISTS", "같은 demand_id가 이미 존재합니다.", 409)
    demand = Demand(**payload.model_dump(), is_active=True)
    session.add(demand)
    session.flush()
    return demand


def update_demand(session: Session, demand_id: str, payload: DemandUpdate) -> Demand:
    demand = get_demand(session, demand_id)
    for field_name, value in payload.model_dump().items():
        setattr(demand, field_name, value)
    demand.is_active = True
    session.flush()
    return demand


def deactivate_demand(session: Session, demand_id: str) -> Demand:
    demand = get_demand(session, demand_id)
    demand.is_active = False
    session.flush()
    return demand


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
    )


def demand_to_index_document(demand: Demand) -> DemandIndexDocument:
    parts = [
        demand.company_name,
        demand.demand_description,
        demand.location,
        " ".join(demand.accepted_conditions),
    ]
    searchable_text = "\n".join(part.strip() for part in parts if part and part.strip())
    return DemandIndexDocument(demand_id=demand.demand_id, searchable_text=searchable_text)


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
