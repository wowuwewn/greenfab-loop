"""Exercise the Golden Workflow against a live FastAPI/PostgreSQL instance."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BASE_URL = os.getenv("GREENFAB_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
CASE_PATH = "/api/v1/cases/SECOM-0116"


def _validate_base_url() -> None:
    parsed = urlparse(BASE_URL)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("GREENFAB_API_BASE_URL must be a local HTTP URL in this CI smoke test")


def request_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = Request(
        BASE_URL + path,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - URL is validated above.
            if response.status != 200:
                raise AssertionError(f"{method} {path} returned HTTP {response.status}")
            decoded = json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise AssertionError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise AssertionError(f"{method} {path} could not reach the API: {exc.reason}") from exc
    if not isinstance(decoded, dict):
        raise AssertionError(f"{method} {path} did not return a JSON object")
    return decoded


def assert_envelope(payload: dict[str, Any]) -> None:
    expected_sections = {
        "case",
        "resource_confirmation",
        "resource_passport",
        "match",
        "decision",
        "esg_scenario",
        "receipt",
    }
    assert set(payload) == expected_sections
    assert payload["case"]["case_id"] == "SECOM-0116"


def main() -> None:
    _validate_base_url()
    initial = request_json(CASE_PATH)
    assert_envelope(initial)
    assert initial["resource_confirmation"]["status"] == "PENDING"

    confirmed = request_json(
        CASE_PATH + "/resource-confirmation",
        method="PUT",
        payload={"status": "CONFIRMED", "confirmed_by": "ci_operator"},
    )
    assert confirmed["resource_confirmation"]["status"] == "CONFIRMED"

    passport = request_json(
        CASE_PATH + "/resource-passport",
        method="PUT",
        payload={
            "description": "반도체 세정 공정에서 회수된 DEMO 미세 무기질 분말",
            "quantity": 12,
            "unit": "kg",
            "condition": "건조 분말",
            "location": "제조동 A",
            "composition": "이산화규소 중심 합성 DEMO 성분표",
        },
        headers={"X-Actor": "ci_operator"},
    )
    assert passport["resource_passport"]["passport_id"] == "PASSPORT-DEMO-0116"

    matched = request_json(
        CASE_PATH + "/matches",
        method="POST",
        payload={"top_k": 3},
        headers={"Idempotency-Key": "ci-golden-match-v1"},
    )
    assert len(matched["match"]["candidates"]) == 3
    assert matched["match"]["candidates"][0]["status"] == "REVIEW"

    duplicate = request_json(
        CASE_PATH + "/matches",
        method="POST",
        payload={"top_k": 3},
        headers={"Idempotency-Key": "ci-golden-match-v1"},
    )
    assert duplicate["match"] == matched["match"]

    decided = request_json(
        CASE_PATH + "/decision",
        method="PUT",
        payload={
            "status": "APPROVED",
            "selected_demand_id": "D01",
            "reason": "CI PostgreSQL Golden Workflow 조건부 승인입니다.",
            "decided_by": "ci_manager",
        },
    )
    assert decided["decision"]["status"] == "APPROVED"

    scenario = request_json(CASE_PATH + "/esg-scenario", method="POST")
    assert scenario["esg_scenario"]["results"] == {
        "candidate_diversion_quantity": 12.0,
        "unit": "kg",
    }

    receipt = request_json(
        CASE_PATH + "/receipt",
        method="POST",
        headers={"Idempotency-Key": "ci-golden-receipt-v1"},
    )
    assert receipt["receipt"]["handoff_status"] == "APPROVED"

    snapshot = request_json(CASE_PATH + "/receipt")
    assert snapshot["receipt"]["receipt_id"] == receipt["receipt"]["receipt_id"]
    print("PostgreSQL Golden Workflow smoke test passed")


if __name__ == "__main__":
    main()
