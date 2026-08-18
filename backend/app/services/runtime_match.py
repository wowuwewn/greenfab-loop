"""Optional real BGE-M3 + ChromaDB Match runtime.

Heavy dependencies are imported only when ``MATCH_PROVIDER=bge_chroma`` is
selected. The default Mock backend and its tests never import or download the
embedding model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any

from app.config import Settings
from app.database import SessionLocal
from app.services.demand import SqlAlchemyDemandCatalog
from app.services.match import (
    DemandIndexDocument,
    IndexSyncResult,
    MatchCandidate,
    MatchProviderError,
    MatchResult,
    MockMatchProvider,
    SemanticSearchHit,
)
from app.services.rules import ResourcePassportInput, evaluate_rules

ModelFactory = Callable[[str, str, str], Any]
ClientFactory = Callable[[], Any]


class BgeM3ChromaAdapter:
    """Dense BGE-M3 embeddings backed by persistent or HTTP ChromaDB."""

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-m3",
        model_revision: str = "5617a9f61b028005a4858fdac845db406aefb181",
        device: str = "cpu",
        batch_size: int = 4,
        collection_name: str = "greenfab_demands",
        chroma_mode: str = "persistent",
        persist_directory: str = ".data/chroma",
        host: str = "localhost",
        port: int = 8001,
        ssl: bool = False,
        headers: dict[str, str] | None = None,
        model_factory: ModelFactory | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_revision = model_revision
        self.device = device
        self.batch_size = batch_size
        self.collection_name = collection_name
        self.chroma_mode = chroma_mode
        self.persist_directory = persist_directory
        self.host = host
        self.port = port
        self.ssl = ssl
        self.headers = headers or {}
        self._model_factory = model_factory or self._default_model_factory
        self._client_factory = client_factory or self._default_client_factory
        self._model: Any | None = None
        self._client: Any | None = None
        self._collection: Any | None = None
        self._model_lock = Lock()
        self._client_lock = Lock()

    @property
    def snapshot_id(self) -> str:
        return f"{self.model_name}@{self.model_revision}:{self.collection_name}"

    def ready(self) -> None:
        client = self._get_client()
        client.heartbeat()
        self._get_collection().count()
        self._get_model()

    def search(self, query_text: str, *, top_k: int) -> Sequence[SemanticSearchHit]:
        query = query_text.strip()
        if not query:
            raise ValueError("Passport search text is empty")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        collection = self._get_collection()
        available = collection.count()
        if available == 0:
            return ()
        response = collection.query(
            query_embeddings=[self._encode([query])[0]],
            n_results=min(top_k, available),
            include=["distances", "metadatas"],
        )
        ids = (response.get("ids") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        raw_metadatas = response.get("metadatas") or []
        metadatas = raw_metadatas[0] if raw_metadatas else [None] * len(ids)
        return tuple(
            SemanticSearchHit(
                demand_id=str(demand_id),
                semantic_similarity=max(-1.0, min(1.0, 1.0 - float(distance))),
                demand_version=(
                    int(metadata["demand_version"])
                    if metadata and metadata.get("demand_version") is not None
                    else None
                ),
                demand_content_sha256=(
                    str(metadata["demand_content_sha256"])
                    if metadata and metadata.get("demand_content_sha256")
                    else None
                ),
            )
            for demand_id, distance, metadata in zip(ids, distances, metadatas, strict=True)
        )

    def upsert(self, documents: Sequence[DemandIndexDocument]) -> int:
        if not documents:
            return 0
        texts = [document.searchable_text for document in documents]
        self._get_collection().upsert(
            ids=[document.demand_id for document in documents],
            documents=texts,
            metadatas=[
                {
                    "demand_id": document.demand_id,
                    **(
                        {"demand_version": document.version} if document.version is not None else {}
                    ),
                    **(
                        {"demand_content_sha256": document.content_sha256}
                        if document.content_sha256
                        else {}
                    ),
                }
                for document in documents
            ],
            embeddings=self._encode(texts),
        )
        return len(documents)

    def delete(self, demand_ids: Sequence[str]) -> int:
        unique_ids = sorted(set(demand_ids))
        if not unique_ids:
            return 0
        self._get_collection().delete(ids=unique_ids)
        return len(unique_ids)

    def list_ids(self) -> set[str]:
        response = self._get_collection().get(include=[])
        return {str(demand_id) for demand_id in response.get("ids", [])}

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._get_model().encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        raw_vectors = vectors.tolist() if hasattr(vectors, "tolist") else vectors
        return [[float(value) for value in vector] for vector in raw_vectors]

    def _get_model(self) -> Any:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    self._model = self._model_factory(
                        self.model_name,
                        self.model_revision,
                        self.device,
                    )
        return self._model

    def _get_client(self) -> Any:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self._client_factory()
        return self._client

    def _get_collection(self) -> Any:
        if self._collection is None:
            client = self._get_client()
            expected_metadata = {
                "hnsw:space": "cosine",
                "embedding_model": self.model_name,
                "embedding_revision": self.model_revision,
            }
            collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata=expected_metadata,
            )
            metadata = getattr(collection, "metadata", None) or {}
            indexed_model = metadata.get("embedding_model")
            indexed_revision = metadata.get("embedding_revision")
            metadata_mismatch = indexed_model not in {
                None,
                self.model_name,
            } or indexed_revision not in {None, self.model_revision}
            collection_count = collection.count()
            metadata_missing = indexed_model is None or indexed_revision is None
            if metadata_mismatch or (collection_count > 0 and metadata_missing):
                raise RuntimeError(
                    "Chroma collection embedding model or revision does not match the "
                    "configured BGE runtime"
                )
            if collection_count == 0 and metadata_missing:
                # Recreating an empty legacy collection is safe and guarantees
                # cosine is the actual HNSW distance, not just a metadata label.
                client.delete_collection(name=self.collection_name)
                collection = client.get_or_create_collection(
                    name=self.collection_name,
                    metadata=expected_metadata,
                )
            self._collection = collection
        return self._collection

    @staticmethod
    def _default_model_factory(model_name: str, model_revision: str, device: str) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised without optional extra
            raise RuntimeError(
                'BGE runtime is not installed; install the backend with ".[match]"'
            ) from exc
        return SentenceTransformer(model_name, revision=model_revision, device=device)

    def _default_client_factory(self) -> Any:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - exercised without optional extra
            raise RuntimeError(
                'Chroma runtime is not installed; install the backend with ".[match]"'
            ) from exc

        if self.chroma_mode == "persistent":
            from chromadb.config import Settings as ChromaSettings

            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            return chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        if self.chroma_mode == "http":
            return chromadb.HttpClient(
                host=self.host,
                port=self.port,
                ssl=self.ssl,
                headers=self.headers or None,
            )
        raise RuntimeError(f"Unsupported CHROMA_MODE: {self.chroma_mode}")


class BgeChromaMatchProvider:
    """Hydrate Chroma hits from PostgreSQL and apply deterministic rules."""

    provider_name = "bge_chroma"

    def __init__(
        self,
        adapter: BgeM3ChromaAdapter,
        catalog: SqlAlchemyDemandCatalog,
        *,
        max_concurrency: int = 1,
        queue_timeout_seconds: int = 30,
    ) -> None:
        self.adapter = adapter
        self.catalog = catalog
        self.model_name = adapter.model_name
        self.snapshot_id = adapter.snapshot_id
        self._inference_slots = BoundedSemaphore(max_concurrency)
        self._queue_timeout_seconds = queue_timeout_seconds
        # The embedding model and local Chroma collection are process-local
        # shared state. Serialize reads/writes so index reconciliation cannot
        # race inference or another mutation in this process.
        self._runtime_lock = Lock()

    def ready(self) -> None:
        self.adapter.ready()

    def match(self, passport: ResourcePassportInput, *, top_k: int = 3) -> MatchResult:
        if not self._inference_slots.acquire(timeout=self._queue_timeout_seconds):
            raise MatchProviderError("Match inference capacity is temporarily exhausted")
        try:
            with self._runtime_lock:
                return self._match(passport, top_k=top_k)
        except MatchProviderError:
            raise
        except Exception as exc:
            raise MatchProviderError("BGE/Chroma Match provider failed") from exc
        finally:
            self._inference_slots.release()

    def _match(self, passport: ResourcePassportInput, *, top_k: int) -> MatchResult:
        query_text = build_passport_search_text(passport)
        # Overfetch protects Top-k from stale/inactive vector IDs. PostgreSQL
        # remains authoritative and the hydrated active rows are sliced below.
        hits = self.adapter.search(query_text, top_k=top_k * 3)
        demand_map = self.catalog.load_active([hit.demand_id for hit in hits])
        candidates: list[MatchCandidate] = []
        for hit in hits:
            demand = demand_map.get(hit.demand_id)
            if demand is None:
                continue
            if (
                hit.demand_version is None
                or hit.demand_content_sha256 is None
                or hit.demand_version != demand.version
                or hit.demand_content_sha256 != demand.content_sha256
            ):
                continue
            candidates.append(
                MatchCandidate(
                    rank=len(candidates) + 1,
                    demand_id=demand.demand_id,
                    company_name=demand.company_name,
                    demand_description=demand.demand_description,
                    semantic_similarity=hit.semantic_similarity,
                    rule_check=evaluate_rules(passport, demand.rules),
                    demand_rules=demand.rules,
                    source_type=demand.source_type,
                    demand_version=demand.version,
                    demand_content_sha256=demand.content_sha256,
                )
            )
            if len(candidates) == top_k:
                break
        if passport.source_type not in {"REAL", "DEMO"}:
            raise ValueError("Passport source_type must be REAL or DEMO")
        source_type = (
            "DEMO"
            if passport.source_type == "DEMO"
            or any(demand.source_type == "DEMO" for demand in demand_map.values())
            else "REAL"
        )
        return MatchResult(
            model=self.model_name,
            created_at=datetime.now(UTC).isoformat(),
            source_type=source_type,
            candidates=tuple(candidates),
            snapshot_id=self.snapshot_id,
        )

    def sync_all_demands(self) -> IndexSyncResult:
        with self._runtime_lock:
            documents = self.catalog.list_active_documents()
            desired_ids = {document.demand_id for document in documents}
            stale_ids = self.adapter.list_ids() - desired_ids
            return IndexSyncResult(
                upserted=self.adapter.upsert(documents),
                deleted=self.adapter.delete(sorted(stale_ids)),
            )

    def upsert_demand(self, demand_id: str) -> None:
        with self._runtime_lock:
            self._reconcile_demand(demand_id)

    def delete_demand(self, demand_id: str) -> None:
        # Re-read PostgreSQL instead of blindly applying an old DELETE event.
        # Delayed mutation attempts therefore converge to the latest state.
        with self._runtime_lock:
            self._reconcile_demand(demand_id)

    def _reconcile_demand(self, demand_id: str) -> None:
        document = self.catalog.load_active_document(demand_id)
        if document is None:
            self.adapter.delete([demand_id])
        else:
            self.adapter.upsert([document])


def build_passport_search_text(passport: ResourcePassportInput) -> str:
    parts = [passport.description, passport.condition, passport.composition]
    query = "\n".join(part.strip() for part in parts if part and part.strip())
    if not query:
        raise ValueError("Passport description, condition, or composition is required")
    return query


def build_match_provider(
    settings: Settings,
    *,
    session_factory: Callable[[], Any] = SessionLocal,
) -> MockMatchProvider | BgeChromaMatchProvider:
    """Construct exactly the configured provider; never fall back silently."""

    if settings.match_provider == "mock":
        return MockMatchProvider()
    if settings.match_provider == "bge_chroma":
        adapter = BgeM3ChromaAdapter(
            model_name=settings.bge_model_name,
            model_revision=settings.bge_model_revision,
            device=settings.bge_device,
            batch_size=settings.bge_batch_size,
            collection_name=settings.chroma_collection_name,
            chroma_mode=settings.chroma_mode,
            persist_directory=settings.chroma_persist_directory,
            host=settings.chroma_host,
            port=settings.chroma_port,
            ssl=settings.chroma_ssl,
            headers=settings.chroma_headers,
        )
        return BgeChromaMatchProvider(
            adapter,
            SqlAlchemyDemandCatalog(session_factory),
            max_concurrency=settings.match_max_concurrency,
            queue_timeout_seconds=settings.match_queue_timeout_seconds,
        )
    raise RuntimeError(f"Unsupported MATCH_PROVIDER: {settings.match_provider}")
