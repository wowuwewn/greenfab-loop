from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, create_database_engine, get_db
from app.main import create_app
from app.seed import seed_demo_data
from app.services.match import MockMatchProvider
from app.storage import LocalEvidenceStorage


@pytest.fixture()
def session_factory():
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
    with factory.begin() as session:
        seed_demo_data(session)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def evidence_storage(tmp_path):
    return LocalEvidenceStorage(tmp_path / "evidence")


@pytest.fixture()
def client(session_factory, evidence_storage):
    app = create_app(
        match_provider=MockMatchProvider(),
        evidence_storage=evidence_storage,
        seed_on_startup=False,
    )

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
