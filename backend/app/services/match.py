"""Matching service contracts and a deterministic offline demo provider.

The API/backend depends on :class:`MatchProvider`, not on BGE-M3 or ChromaDB.
The included :class:`MockMatchProvider` serves a fixed, precomputed DEMO
snapshot and performs only the pure rules from ``rules.py``.  It makes the MVP
and tests work without network, CUDA, model downloads, or a vector database.

Production integration boundary
--------------------------------
An infrastructure adapter can implement :class:`SemanticSearchAdapter` by
loading ``BAAI/bge-m3`` once (CPU by default, optional CUDA by configuration)
and querying ChromaDB.  It then feeds the returned ``DemandSnapshot`` objects
through the same rule evaluator.  Neither this module nor ``rules.py`` imports
``torch``, ``sentence_transformers``, or ``chromadb``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from .rules import DemandRules, ResourcePassportInput, RuleCheck, evaluate_rules


class MatchProviderError(RuntimeError):
    """Safe boundary error raised by Match infrastructure adapters."""


@dataclass(frozen=True, slots=True)
class DemandSnapshot:
    """A demand returned by semantic retrieval plus its deterministic rules."""

    demand_id: str
    company_name: str
    demand_description: str
    semantic_similarity: float
    rules: DemandRules
    source_type: Literal["REAL", "DEMO"] = "DEMO"
    version: int | None = None
    content_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticSearchHit:
    """Vector retrieval output; business fields remain in PostgreSQL."""

    demand_id: str
    semantic_similarity: float
    demand_version: int | None = None
    demand_content_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class DemandIndexDocument:
    """Minimal PostgreSQL projection written to the disposable vector index."""

    demand_id: str
    searchable_text: str
    version: int | None = None
    content_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class IndexSyncResult:
    upserted: int
    deleted: int


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    rank: int
    demand_id: str
    company_name: str
    demand_description: str
    semantic_similarity: float
    rule_check: RuleCheck
    demand_rules: DemandRules
    source_type: Literal["REAL", "DEMO"] = "DEMO"
    demand_version: int | None = None
    demand_content_sha256: str | None = None

    @property
    def status(self) -> str:
        return self.rule_check.status

    def as_dict(self) -> dict[str, object]:
        return {
            "demand_id": self.demand_id,
            "company_name": self.company_name,
            "demand_description": self.demand_description,
            "semantic_similarity": self.semantic_similarity,
            "rule_check": self.rule_check.as_dict(),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class MatchResult:
    model: str
    created_at: str
    source_type: Literal["REAL", "DEMO"]
    candidates: tuple[MatchCandidate, ...]
    snapshot_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "created_at": self.created_at,
            "source_type": self.source_type,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


@runtime_checkable
class MatchProvider(Protocol):
    """The sole matching boundary consumed by workflow/backend code."""

    def match(
        self,
        passport: ResourcePassportInput,
        *,
        top_k: int = 3,
    ) -> MatchResult:
        """Return ranked semantic candidates enriched with deterministic rules."""

    def ready(self) -> None:
        """Raise RuntimeError when the configured provider cannot serve requests."""


@runtime_checkable
class SemanticSearchAdapter(Protocol):
    """Boundary implemented by the optional CPU-first BGE-M3 + Chroma runtime.

    The adapter owns model/vector-store lifecycle and must return already ranked
    candidates.  Device selection and Chroma persistence stay outside the pure
    matching domain; production configuration should default ``device`` to
    ``"cpu"`` and opt into CUDA explicitly.
    """

    model_name: str
    device: str

    def ready(self) -> None:
        """Load the model once and verify the vector-store connection."""

    def search(self, query_text: str, *, top_k: int) -> Sequence[SemanticSearchHit]:
        """Retrieve demand IDs and dense-vector similarity only."""

    def upsert(self, documents: Sequence[DemandIndexDocument]) -> int:
        """Embed and upsert documents by demand_id."""

    def delete(self, demand_ids: Sequence[str]) -> int:
        """Remove inactive or deleted demand IDs from the vector index."""

    def list_ids(self) -> set[str]:
        """Return every demand_id currently present in the vector index."""

    def list_indexed_documents(self) -> dict[str, tuple[int | None, str | None]]:
        """Return indexed Demand lineage as ``id -> (version, content hash)``."""


@runtime_checkable
class DemandIndexManager(Protocol):
    """Capability implemented by providers backed by a Demand vector index."""

    provider_name: str

    def sync_all_demands(self) -> IndexSyncResult:
        """Reconcile the complete index from PostgreSQL source-of-truth rows."""

    def upsert_demand(self, demand_id: str) -> None:
        """Re-index one active PostgreSQL Demand."""

    def delete_demand(self, demand_id: str) -> None:
        """Delete one inactive Demand from the vector index."""


_DEMO_SNAPSHOT_ID = "greenfab-loop-synthetic-v1@2026-08-16"
_DEMO_CREATED_AT = "2026-08-16T15:56:47.692Z"

# Fixed scores are an offline snapshot of the DEMO experience, not runtime
# inference, industrial suitability, safety, or recycling-success probability.
_DEMO_TOP3: tuple[DemandSnapshot, ...] = (
    DemandSnapshot(
        demand_id="D01",
        company_name="제주 세라믹랩",
        demand_description=(
            "세라믹 복합재 연구를 위해 규소계 미분말을 5~20kg 단위로 찾고 있음. "
            "성분표 확인과 실험실 적합성 시험 후 소량 파일럿 사용 가능."
        ),
        semantic_similarity=0.649156,
        rules=DemandRules(
            quantity_min=5.0,
            quantity_max=20.0,
            unit="kg",
            required_fields=("description", "quantity", "unit", "composition"),
        ),
        version=1,
        content_sha256="d8d7f4796d17da7b44f549ab8b5a9d8d0d4d3a2766474f938033cf0ce7dedf64",
    ),
    DemandSnapshot(
        demand_id="D15",
        company_name="시멘트서큘러랩",
        demand_description=(
            "건조된 무기성 침전물 중 칼슘 함량이 높은 재료를 소성 시험용 "
            "보조 원료로 검토. 유해성 분석 필수."
        ),
        semantic_similarity=0.629172,
        rules=DemandRules(
            required_fields=("description", "composition", "condition"),
        ),
        version=1,
        content_sha256="72eeef919ca8441ce4d7a8362c75dc0877c4e4f3612ca94b867cee1b6f5c8764",
    ),
    DemandSnapshot(
        demand_id="D11",
        company_name="제주메탈리턴",
        demand_description=(
            "합금 계열이 확인되고 절삭유이 제거된 경량 금속 칩을 재용해 원료로 매입."
        ),
        semantic_similarity=0.60239,
        rules=DemandRules(
            required_fields=("description", "composition", "condition"),
        ),
        version=1,
        content_sha256="ed1a90b049cf55b016e9b96ab01f3877dfa3bf87001d57b99e493ee33dc0957c",
    ),
)


class MockMatchProvider:
    """Offline provider backed by a stable DEMO Top-3 semantic snapshot."""

    model_name = "Xenova/bge-m3"
    snapshot_id = _DEMO_SNAPSHOT_ID
    provider_name = "mock"

    def ready(self) -> None:
        """The frozen offline snapshot has no external dependency."""

    def match(
        self,
        passport: ResourcePassportInput,
        *,
        top_k: int = 3,
    ) -> MatchResult:
        if not 1 <= top_k <= len(_DEMO_TOP3):
            raise ValueError(f"top_k must be between 1 and {len(_DEMO_TOP3)}")
        if not _is_golden_snapshot_input(passport):
            raise ValueError("MockMatchProvider supports only the Golden R01 semantic snapshot")

        candidates = tuple(
            MatchCandidate(
                rank=rank,
                demand_id=demand.demand_id,
                company_name=demand.company_name,
                demand_description=demand.demand_description,
                semantic_similarity=demand.semantic_similarity,
                rule_check=evaluate_rules(passport, demand.rules),
                demand_rules=demand.rules,
                source_type=demand.source_type,
                demand_version=demand.version,
                demand_content_sha256=demand.content_sha256,
            )
            for rank, demand in enumerate(_DEMO_TOP3[:top_k], start=1)
        )
        return MatchResult(
            model=self.model_name,
            created_at=_DEMO_CREATED_AT,
            source_type="DEMO",
            candidates=candidates,
            snapshot_id=self.snapshot_id,
        )


def _is_golden_snapshot_input(passport: ResourcePassportInput) -> bool:
    """Prevent a frozen R01 score snapshot from being shown for unrelated inputs."""

    description = " ".join((passport.description or "").casefold().split())
    return all(keyword in description for keyword in ("반도체", "세정", "무기질"))
