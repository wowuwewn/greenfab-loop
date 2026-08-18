from __future__ import annotations

import pytest

from app.config import Settings
from app.services.match import (
    DemandIndexDocument,
    DemandSnapshot,
    IndexSyncResult,
    SemanticSearchHit,
)
from app.services.rules import DemandRules, ResourcePassportInput
from app.services.runtime_match import (
    BgeChromaMatchProvider,
    BgeM3ChromaAdapter,
    build_match_provider,
)


class FakeArray:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeModel:
    def __init__(self) -> None:
        self.calls = 0
        self.last_kwargs = None

    def encode(self, texts, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return FakeArray([[float(index + 1), 0.5] for index, _text in enumerate(texts)])


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, str] = {}
        self.last_query = None

    def count(self):
        return len(self.documents)

    def upsert(self, *, ids, documents, metadatas, embeddings):
        assert [metadata["demand_id"] for metadata in metadatas] == ids
        assert len(embeddings) == len(ids)
        self.documents.update(dict(zip(ids, documents, strict=True)))

    def delete(self, *, ids):
        for demand_id in ids:
            self.documents.pop(demand_id, None)

    def get(self, *, include):
        assert include == []
        return {"ids": list(self.documents)}

    def query(self, **kwargs):
        self.last_query = kwargs
        return {"ids": [["D01", "D15"]], "distances": [[0.1, 0.4]]}


class FakeClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.heartbeats = 0

    def heartbeat(self):
        self.heartbeats += 1

    def get_or_create_collection(self, *, name, metadata):
        assert name == "test-demands"
        assert metadata["hnsw:space"] == "cosine"
        assert metadata["embedding_revision"] == ("5617a9f61b028005a4858fdac845db406aefb181")
        if not hasattr(self.collection, "metadata"):
            self.collection.metadata = metadata
        return self.collection


def test_adapter_loads_model_once_and_keeps_only_demand_ids_in_chroma() -> None:
    model = FakeModel()
    collection = FakeCollection()
    client = FakeClient(collection)
    factory_calls = 0

    def model_factory(model_name, model_revision, device):
        nonlocal factory_calls
        factory_calls += 1
        assert model_name == "BAAI/bge-m3"
        assert model_revision == "5617a9f61b028005a4858fdac845db406aefb181"
        assert device == "cpu"
        return model

    adapter = BgeM3ChromaAdapter(
        collection_name="test-demands",
        model_factory=model_factory,
        client_factory=lambda: client,
    )
    adapter.ready()
    adapter.ready()
    assert factory_calls == 1
    assert client.heartbeats == 2
    assert adapter.snapshot_id == (
        "BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181:test-demands"
    )

    indexed = adapter.upsert(
        [
            DemandIndexDocument("D01", "규소계 미분말"),
            DemandIndexDocument("D15", "무기성 침전물"),
        ]
    )
    assert indexed == 2
    assert adapter.list_ids() == {"D01", "D15"}
    hits = adapter.search("실리콘 분말", top_k=3)
    assert model.last_kwargs["normalize_embeddings"] is True
    assert model.last_kwargs["batch_size"] == 4
    assert collection.last_query["n_results"] == 2
    assert hits == (
        SemanticSearchHit("D01", 0.9),
        SemanticSearchHit("D15", 0.6),
    )
    assert adapter.delete(["D15"]) == 1
    assert adapter.list_ids() == {"D01"}


def test_adapter_rejects_nonempty_collection_from_another_embedding_model() -> None:
    collection = FakeCollection()
    collection.documents["OLD"] = "legacy embedding"
    collection.metadata = {"embedding_model": "another/model"}
    adapter = BgeM3ChromaAdapter(
        collection_name="test-demands",
        model_factory=lambda _model_name, _model_revision, _device: FakeModel(),
        client_factory=lambda: FakeClient(collection),
    )

    with pytest.raises(RuntimeError, match="embedding model or revision"):
        adapter.ready()


def test_adapter_rejects_nonempty_collection_from_another_model_revision() -> None:
    collection = FakeCollection()
    collection.documents["OLD"] = "legacy embedding"
    collection.metadata = {
        "hnsw:space": "cosine",
        "embedding_model": "BAAI/bge-m3",
        "embedding_revision": "old-revision",
    }
    adapter = BgeM3ChromaAdapter(
        collection_name="test-demands",
        model_factory=lambda _model_name, _model_revision, _device: FakeModel(),
        client_factory=lambda: FakeClient(collection),
    )

    with pytest.raises(RuntimeError, match="model or revision"):
        adapter.ready()


class FakeAdapter:
    model_name = "BAAI/bge-m3"
    device = "cpu"
    snapshot_id = "BAAI/bge-m3@test"

    def __init__(self) -> None:
        self.ids = {"STALE"}
        self.upserts: list[list[str]] = []

    def ready(self):
        return None

    def search(self, _query_text, *, top_k):
        assert top_k == 2
        return [SemanticSearchHit("D01", 0.91), SemanticSearchHit("D15", 0.72)]

    def upsert(self, documents):
        ids = [document.demand_id for document in documents]
        self.upserts.append(ids)
        self.ids.update(ids)
        return len(ids)

    def delete(self, demand_ids):
        for demand_id in demand_ids:
            self.ids.discard(demand_id)
        return len(demand_ids)

    def list_ids(self):
        return set(self.ids)


class FakeCatalog:
    def __init__(self, demand_source_type="REAL") -> None:
        self.snapshots = {
            "D01": DemandSnapshot(
                demand_id="D01",
                company_name="세라믹랩",
                demand_description="규소계 분말 수요",
                semantic_similarity=0,
                rules=DemandRules(
                    quantity_min=5,
                    quantity_max=20,
                    unit="kg",
                    required_fields=("description", "quantity", "unit", "composition"),
                ),
                source_type=demand_source_type,
            ),
            "D15": DemandSnapshot(
                demand_id="D15",
                company_name="시멘트랩",
                demand_description="무기성 원료 수요",
                semantic_similarity=0,
                rules=DemandRules(required_fields=("description", "condition")),
                source_type=demand_source_type,
            ),
        }

    def load_active(self, demand_ids):
        return {demand_id: self.snapshots[demand_id] for demand_id in demand_ids}

    def list_active_documents(self):
        return [
            DemandIndexDocument(demand_id, snapshot.demand_description)
            for demand_id, snapshot in self.snapshots.items()
        ]

    def load_active_document(self, demand_id):
        snapshot = self.snapshots.get(demand_id)
        return (
            DemandIndexDocument(demand_id, snapshot.demand_description)
            if snapshot is not None
            else None
        )


def test_real_provider_hydrates_postgres_rules_and_reconciles_stale_ids() -> None:
    adapter = FakeAdapter()
    provider = BgeChromaMatchProvider(adapter, FakeCatalog())
    result = provider.match(
        ResourcePassportInput(
            passport_id="P-1",
            description="세정 공정 규소계 분말",
            quantity=12,
            unit="kg",
            condition="건조",
            composition="규소 95%",
            source_type="REAL",
        ),
        top_k=2,
    )
    assert result.source_type == "REAL"
    assert result.model == "BAAI/bge-m3"
    assert [candidate.demand_id for candidate in result.candidates] == ["D01", "D15"]
    assert [candidate.semantic_similarity for candidate in result.candidates] == [0.91, 0.72]
    assert result.candidates[0].status == "REVIEW"

    assert provider.sync_all_demands() == IndexSyncResult(upserted=2, deleted=1)
    assert adapter.ids == {"D01", "D15"}


def test_real_provider_marks_match_demo_when_any_demand_is_demo() -> None:
    provider = BgeChromaMatchProvider(FakeAdapter(), FakeCatalog("DEMO"))

    result = provider.match(
        ResourcePassportInput(
            passport_id="P-1",
            description="세정 공정 규소계 분말",
            condition="건조",
            composition="규소 95%",
            source_type="REAL",
        ),
        top_k=2,
    )

    assert result.source_type == "DEMO"


def test_provider_factory_keeps_heavy_runtime_optional() -> None:
    provider = build_match_provider(Settings(match_provider="mock"))
    assert provider.provider_name == "mock"

    configured = build_match_provider(Settings(match_provider="bge_chroma"))
    assert isinstance(configured, BgeChromaMatchProvider)
    assert configured.adapter.model_revision == ("5617a9f61b028005a4858fdac845db406aefb181")
    # Construction itself must not import sentence-transformers/chromadb or load weights.
    assert configured.adapter._model is None
    assert configured.adapter._client is None
