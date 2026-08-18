"""Run the Golden Core API workflow against the real configured BGE provider.

Use only with an isolated SQLite DATABASE_URL and an isolated persistent Chroma
directory. The script creates missing tables but never drops existing data.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import app.models  # noqa: F401 - registers SQLAlchemy metadata
from app.database import Base, engine
from app.main import app


def main() -> None:
    from fastapi.testclient import TestClient

    Base.metadata.create_all(engine)
    provider = app.state.match_provider
    adapter = getattr(provider, "adapter", None)
    trace = {"encode_calls": 0, "encoded_text_count": 0, "adapter_search_calls": 0}

    if adapter is None:
        raise RuntimeError("Configured provider is not the BGE/Chroma runtime")

    original_encode = adapter._encode
    original_search = adapter.search

    def traced_encode(texts: Sequence[str]) -> list[list[float]]:
        trace["encode_calls"] += 1
        trace["encoded_text_count"] += len(texts)
        return original_encode(texts)

    def traced_search(query_text: str, *, top_k: int):
        trace["adapter_search_calls"] += 1
        return original_search(query_text, top_k=top_k)

    adapter._encode = traced_encode
    adapter.search = traced_search

    statuses: dict[str, int] = {}
    with TestClient(app) as client:
        health = client.get("/health/ready")
        statuses["health_ready"] = health.status_code
        reset = client.post("/api/v1/demo/reset")
        statuses["demo_reset"] = reset.status_code
        if reset.status_code != 200:
            raise RuntimeError(f"Demo reset failed: {reset.status_code} {reset.text}")
        confirmation = client.put(
            "/api/v1/cases/SECOM-0116/resource-confirmation",
            json={"status": "CONFIRMED", "confirmed_by": "demo_operator"},
        )
        statuses["resource_confirmation"] = confirmation.status_code
        if confirmation.status_code != 200:
            raise RuntimeError(
                f"Resource confirmation failed: {confirmation.status_code} {confirmation.text}"
            )
        passport = client.put(
            "/api/v1/cases/SECOM-0116/resource-passport",
            json={
                "description": "반도체 세정 공정에서 회수된 DEMO 미세 무기질 분말",
                "quantity": 12,
                "unit": "kg",
                "condition": "건조 분말",
                "location": "제조동 A",
                "composition": "이산화규소 중심 합성 DEMO 성분표",
            },
        )
        statuses["resource_passport"] = passport.status_code
        if passport.status_code != 200:
            raise RuntimeError(f"Resource Passport failed: {passport.status_code} {passport.text}")
        match_response = client.post(
            "/api/v1/cases/SECOM-0116/matches",
            json={"top_k": 3},
            headers={"Idempotency-Key": "actual-bge-final-v1"},
        )
        statuses["match"] = match_response.status_code
        if match_response.status_code != 200:
            raise RuntimeError(match_response.text)
        match = match_response.json()["match"]
        reviewable = next(
            candidate for candidate in match["candidates"] if candidate["status"] == "REVIEW"
        )
        decision = client.put(
            "/api/v1/cases/SECOM-0116/decision",
            json={
                "status": "APPROVED",
                "selected_demand_id": reviewable["demand_id"],
                "reason": "성분 분석 완료 후 파일럿 검토를 진행합니다.",
                "decided_by": "demo_manager",
            },
        )
        statuses["decision"] = decision.status_code
        if decision.status_code != 200:
            raise RuntimeError(f"Decision failed: {decision.status_code} {decision.text}")
        scenario = client.post(
            "/api/v1/cases/SECOM-0116/esg-scenario",
            json={
                "scenario_quantity_kg": 12,
                "baseline_pathway": "기존 폐기 처리",
                "alternative_pathway": "세라믹 원료 파일럿 활용",
                "baseline_energy_factor_kwh_per_kg": None,
                "alternative_energy_factor_kwh_per_kg": None,
                "baseline_carbon_factor_kgco2e_per_kg": None,
                "alternative_carbon_factor_kgco2e_per_kg": None,
                "factor_source": None,
            },
        )
        statuses["esg_scenario"] = scenario.status_code
        if scenario.status_code != 200:
            raise RuntimeError(f"ESG Scenario failed: {scenario.status_code} {scenario.text}")
        receipt = client.post(
            "/api/v1/cases/SECOM-0116/receipt",
            headers={"Idempotency-Key": "actual-bge-final-receipt-v1"},
        )
        statuses["receipt"] = receipt.status_code
        if receipt.status_code != 200:
            raise RuntimeError(f"Receipt failed: {receipt.status_code} {receipt.text}")
        receipt_id = receipt.json()["receipt"]["receipt_id"]
        verify = client.get(f"/api/v1/receipts/{receipt_id}")
        statuses["receipt_verify"] = verify.status_code
        if verify.status_code != 200:
            raise RuntimeError(f"Receipt verify failed: {verify.status_code} {verify.text}")

    output: dict[str, Any] = {
        "provider": provider.__class__.__name__,
        "provider_name": provider.provider_name,
        "model": match["model"],
        "model_revision": match["model_revision"],
        "device": adapter.device,
        "chroma_mode": adapter.chroma_mode,
        "chroma_collection_count": adapter._get_collection().count(),
        "health_ready": health.json(),
        "http_statuses": statuses,
        "execution_trace": trace,
        "match_source_type": match["source_type"],
        "candidates": [
            {
                "rank": rank,
                "demand_id": candidate["demand_id"],
                "company_name": candidate["company_name"],
                "semantic_similarity": candidate["semantic_similarity"],
                "quantity_rule": candidate["rule_check"]["quantity"],
                "required_info_rule": candidate["rule_check"]["required_info"],
                "location_rule": candidate["rule_check"]["location"],
                "status": candidate["status"],
            }
            for rank, candidate in enumerate(match["candidates"], start=1)
        ],
        "decision": decision.json()["decision"],
        "esg_scenario": scenario.json()["esg_scenario"],
        "receipt": receipt.json()["receipt"],
        "receipt_verify_matches_snapshot": verify.json() == receipt.json(),
        "mock_fallback_occurred": provider.provider_name == "mock",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
