# GreenFab Loop Backend API Contract v0.1

## 1. 공통 규칙

- Base path: `/api/v1`
- Content type: `application/json`
- 필드명: `snake_case`
- 시간: timezone을 포함한 ISO 8601
- 상세 Case 응답: [`data-contract.md`](./data-contract.md)의 7개 top-level key
- 아직 도달하지 않은 단계: `null`
- `source_type`: `REAL`, `DEMO`, `SCENARIO`만 허용
- 상태 변경 API: 성공 시 최신 전체 Case envelope 반환
- 응답의 `X-Trace-Id`: 요청 추적 ID. 요청에서 같은 헤더를 보내면 재사용
- 요청 문자열은 앞뒤 공백을 제거하며, `confirmed_by`, Passport `description`, Decision `reason`·`decided_by` 같은 필수 문자열은 공백만 입력하면 `422 VALIDATION_ERROR`
- Workflow 변경 API는 PostgreSQL에서 대상 Case를 `SELECT ... FOR UPDATE`로 잠근 뒤 상태를 검사

인증·권한은 MVP 비범위입니다. `confirmed_by`, `decided_by` 또는 `X-Actor`로 actor를 받으며 운영 전에는 인증 주체에서 가져오도록 변경해야 합니다.

### Case envelope

```json
{
  "case": {},
  "resource_confirmation": null,
  "resource_passport": null,
  "match": null,
  "decision": null,
  "esg_scenario": null,
  "receipt": null
}
```

내부 `workflow_status`는 목록 조회용 summary에는 포함되지만 Data Contract v0.1의 상세 `case` 객체에는 추가하지 않습니다.

## 2. 공통 오류

```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "자원 발생 확인 후에만 Passport를 저장할 수 있습니다.",
    "field_errors": [],
    "trace_id": "8ef2538c-42c1-4f17-8a40-c13e59ff8ab9"
  }
}
```

주요 오류:

| HTTP | `code` | 의미 |
| --- | --- | --- |
| 404 | `CASE_NOT_FOUND` | Case가 없음 |
| 404 | `RECEIPT_NOT_FOUND` | Receipt가 없음 |
| 404 | `NOT_FOUND` | Demo reset 등 비활성 기능 |
| 409 | `INVALID_STATE` | 현재 Workflow 단계에서 허용되지 않음 |
| 409 | `INVALID_CANDIDATE` | 최신 Match에 없는 후보를 선택 |
| 409 | `CANDIDATE_NOT_REVIEWABLE` | `REVIEW`가 아닌 후보를 승인하려 함 |
| 409 | `RECEIPT_ALREADY_EXISTS` | 기존 Receipt와 다른 key로 다시 생성하려 함 |
| 422 | `VALIDATION_ERROR` | Pydantic 필드·도메인 검증 실패 |
| 503 | `MATCH_UNAVAILABLE` | 주입된 Match Provider 실행 실패 |
| 503 | `DATABASE_UNAVAILABLE` | SQLAlchemy/PostgreSQL 요청 처리 실패 |
| 500 | `INTEGRITY_ERROR`, `MATCH_DATA_ERROR` | 저장 관계 또는 DEMO Demand가 불완전함 |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 예외의 안전한 공통 응답 |

FastAPI 기본 422도 위 형식으로 정규화합니다. API router는 404, 409, 422, 500, 503의 공통 `ErrorResponse`를 OpenAPI에 선언합니다. 내부 stack trace와 비밀값은 응답하지 않고 서버 log에 `trace_id`와 함께 기록합니다.

## 3. Actor와 중복 요청

- Passport, Match, ESG Scenario, Receipt는 선택적 `X-Actor`를 받으며 기본값은 `demo_operator`입니다.
- Match와 Receipt는 선택적 `Idempotency-Key`를 지원합니다. Frontend에서는 중복 클릭 방지를 위해 항상 보내는 것을 권장합니다.
- `X-Actor`는 공백 이외 문자를 포함한 1–120자, `Idempotency-Key`는 공백 이외 문자를 포함한 1–255자여야 합니다. 공백-only 또는 길이 초과 header는 `422`입니다.
- 요청 `X-Trace-Id`는 trim 후 1–64자일 때만 사용합니다. 비어 있거나 64자를 넘으면 요청을 실패시키지 않고 서버가 안전한 UUID를 새로 생성합니다.
- Match key는 Case 범위이며 같은 Case의 같은 key는 기존 상태를 반환합니다. 다른 Case에서는 같은 문자열을 사용할 수 있습니다.
- Receipt도 Case 범위이며 다른 Case에서 같은 key 문자열을 사용할 수 있습니다. 같은 key 또는 key 없이 재호출하면 기존 Receipt를 반환합니다. 기존 Receipt가 key와 함께 생성됐는데 같은 Case에서 다른 non-null key로 재생성하면 `409 RECEIPT_ALREADY_EXISTS`입니다.
- 같은 Case의 동시 재시도는 Case row lock과 DB Unique 제약으로 한 건만 유지합니다.
- ESG Scenario도 Case당 하나이며 재호출하면 기존 결과를 반환합니다.

현재 구현은 범용 request hash를 저장하지 않습니다. 같은 key를 다른 본문에 재사용하지 않는 것은 Client 책임이며, 운영 전 범용 idempotency 저장소를 추가해야 합니다.

## 4. Health API

### `GET /health` 또는 `GET /health/live`

```json
{"status": "ok", "database": null, "match_provider": null}
```

### `GET /health/ready`

PostgreSQL `SELECT 1`을 실행하고 주입된 Provider class를 표시합니다.

```json
{
  "status": "ready",
  "database": "ok",
  "match_provider": "MockMatchProvider"
}
```

## 5. Case API

### `GET /api/v1/cases`

현재 MVP의 전체 Case summary 목록을 단순 배열로 반환합니다.

```json
[
  {
    "case_id": "SECOM-0116",
    "risk_rank": 4,
    "source_type": "REAL",
    "workflow_status": "CONFIRMATION_PENDING",
    "updated_at": "2026-08-18T12:00:00+09:00"
  }
]
```

Pagination과 검색 필터는 후속 범위입니다.

### `GET /api/v1/cases/{case_id}`

Response `200`: 전체 Case envelope
Errors: `404 CASE_NOT_FOUND`

## 6. Resource confirmation API

### `PUT /api/v1/cases/{case_id}/resource-confirmation`

```json
{
  "status": "CONFIRMED",
  "confirmed_by": "demo_operator"
}
```

- 입력 `status`: `CONFIRMED`, `NOT_CONFIRMED`. `PENDING`은 서버 초기 상태입니다.
- `source_type`은 서버가 MVP에서 `DEMO`로 유지합니다.
- 서버가 `confirmed_at`을 생성합니다.
- 완료 상태는 trim 후 비어 있지 않은 `confirmed_by`와 `confirmed_at`을 함께 가져야 하며 DB Check Constraint도 같은 조건을 보장합니다.
- `NOT_CONFIRMED`이면 Case가 `CLOSED`로 끝나고 이후 객체는 `null`입니다.
- 같은 상태와 확인자를 다시 보내면 기존 결과를 반환합니다.

Response `200`: 최신 Case envelope
Errors: `404 CASE_NOT_FOUND`, `409 INVALID_STATE`, `422 VALIDATION_ERROR`

## 7. Resource Passport API

### `PUT /api/v1/cases/{case_id}/resource-passport`

Headers: `X-Actor` 선택

```json
{
  "description": "반도체 세정 공정에서 회수된 DEMO 미세 무기질 분말",
  "quantity": 12,
  "unit": "kg",
  "condition": "건조 분말",
  "location": "제조동 A",
  "composition": "이산화규소 중심 합성 DEMO 성분표"
}
```

- `RESOURCE_CONFIRMED`, `PASSPORT_READY`에서만 허용합니다.
- `description`은 필수이며 비어 있을 수 없습니다.
- `quantity`와 `unit`은 함께 존재하거나 함께 `null`이어야 합니다. 수량만 또는 단위만 보내면 `422`입니다.
- 문자열은 trim되며 공백뿐인 `description`이나 `unit`은 거부됩니다.
- 모르는 선택 필드는 `null`로 보냅니다.
- `source_type`과 `passport_id`는 서버가 DEMO 규칙으로 생성합니다.
- Match 이후 Passport 수정은 현재 MVP에서 차단합니다.

Response `200`: 최신 Case envelope
Errors: `404 CASE_NOT_FOUND`, `409 INVALID_STATE`, `422 VALIDATION_ERROR`

## 8. Match API

### `POST /api/v1/cases/{case_id}/matches`

Headers: `Idempotency-Key`, `X-Actor` 선택

```json
{"top_k": 3}
```

- `top_k`: 1–3, 기본 3
- `PASSPORT_READY` 또는 Decision 전 `MATCH_READY`에서 실행합니다.
- Match Run과 후보, deterministic Rule 결과를 같은 DB 트랜잭션으로 저장합니다.
- 기본 Provider는 `MockMatchProvider`이며 BGE-M3로 사전 생성해 고정한 DEMO Top-3 snapshot을 반환합니다.
- snapshot 점수는 현재 요청의 runtime 추론값이 아니며 모델명과 snapshot revision을 내부 Match Run에 함께 저장합니다.
- 응답 `match.created_at`은 snapshot 생성시각이 아니라 현재 Match Run의 `completed_at`입니다.
- Mock은 Golden R01 snapshot 전용입니다. Passport `description`에 `반도체`, `세정`, `무기질`이 모두 없으면 무관한 고정 점수를 표시하지 않고 `503 MATCH_UNAVAILABLE`를 반환합니다.
- Golden signature가 없는 자유 입력 검색에는 실제 BGE-M3/ChromaDB Adapter가 필요합니다.

Response `200`: 최신 Case envelope
Errors: `409 INVALID_STATE`, `503 MATCH_UNAVAILABLE`, `500 MATCH_DATA_ERROR`

Golden Match 예시:

```json
{
  "model": "Xenova/bge-m3",
  "created_at": "2026-08-18T12:03:15+09:00",
  "source_type": "DEMO",
  "candidates": [
    {
      "demand_id": "D01",
      "company_name": "제주 세라믹랩",
      "demand_description": "DEMO 수요 설명",
      "semantic_similarity": 0.649156,
      "rule_check": {
        "quantity": true,
        "required_info": true,
        "location": null,
        "missing_fields": []
      },
      "status": "REVIEW"
    }
  ]
}
```

Rule status 우선순위:

1. 수량·위치처럼 명시적으로 검사된 조건이 `false`이면 `RULE_FAIL`
2. `required_info: false` 또는 `missing_fields`가 있으면 `NEEDS_INFO`
3. 그 외는 `REVIEW`

`null`은 미평가·비적용일 수 있으며 그 자체로 `NEEDS_INFO`가 되지 않습니다.

## 9. Human Decision API

### `PUT /api/v1/cases/{case_id}/decision`

```json
{
  "status": "APPROVED",
  "selected_demand_id": "D01",
  "reason": "성분 분석 완료 후 파일럿 검토를 진행합니다.",
  "decided_by": "demo_manager"
}
```

- `MATCH_READY` 또는 Scenario 전 `DECIDED`에서 허용합니다.
- `reason`은 10자 이상이며 모든 Decision에 필요합니다.
- `APPROVED`에는 최신 Match 후보의 `selected_demand_id`가 필요합니다.
- 현재 MVP에서는 `REVIEW` 후보만 승인할 수 있습니다.
- Backend는 선택한 `demand_id`와 함께 내부 `selected_match_candidate_id` FK를 저장해 실제 검토 후보까지 추적합니다.
- `NEEDS_INFO`, `RULE_FAIL` override는 구현하지 않습니다.
- 서버가 `decided_at`을 생성합니다.

Response `200`: 최신 Case envelope
Errors: `409 INVALID_STATE`, `409 INVALID_CANDIDATE`, `409 CANDIDATE_NOT_REVIEWABLE`, `422 VALIDATION_ERROR`

## 10. ESG Scenario API

### `POST /api/v1/cases/{case_id}/esg-scenario`

Headers: `X-Actor` 선택
Request body: 없음

```json
{
  "source_type": "SCENARIO",
  "inputs": {
    "resource_quantity": 12,
    "unit": "kg",
    "decision_status": "APPROVED"
  },
  "results": {
    "candidate_diversion_quantity": 12,
    "unit": "kg"
  },
  "formula_version": "candidate_diversion_v0.1",
  "factor_source": null
}
```

- `DECIDED`, `SCENARIO_READY`에서 허용합니다.
- Case당 하나이며 재호출하면 기존 Scenario를 반환합니다.
- 내부 `decision_id` FK로 Scenario 계산에 사용한 정확한 Decision을 연결합니다.
- `APPROVED`이고 수량을 알면 후보 전환량은 Passport 수량입니다.
- `APPROVED`이고 수량을 모르면 `candidate_diversion_quantity`는 `null`입니다.
- `HOLD`, `REJECTED`이면 후보 전환량은 0입니다.
- 실제 전환, CO2e, 비용 절감 값을 만들지 않습니다.

Response `200`: 최신 Case envelope
Errors: `409 INVALID_STATE`

## 11. Green Receipt API

### `POST /api/v1/cases/{case_id}/receipt`

Headers: `Idempotency-Key`, `X-Actor` 선택
Request body: 없음

- `SCENARIO_READY`, `RECEIPT_CREATED`에서 허용합니다.
- Case, Confirmation, Passport, 최신 Match, Decision, Scenario를 JSONB 스냅샷으로 저장합니다.
- 내부 `decision_id`, `scenario_id` FK도 저장해 Receipt의 의사결정·계산 lineage를 관계형으로 보장합니다.
- 승인 흐름은 `handoff_status: APPROVED`, HOLD/REJECTED는 `RESOURCE_CONFIRMED`입니다.
- MVP에서는 `HANDOFF_CONFIRMED`를 만들지 않습니다.

Response `200`: 최신 Case envelope
Errors: `409 INVALID_STATE`, `409 RECEIPT_ALREADY_EXISTS`

### `GET /api/v1/cases/{case_id}/receipt`

현재 Case를 다시 조립하지 않고 Receipt 생성 시 저장한 immutable-style 전체 `CaseEnvelope` snapshot을 반환합니다.

```json
{
  "case": {},
  "resource_confirmation": {},
  "resource_passport": {},
  "match": {},
  "decision": {},
  "esg_scenario": {},
  "receipt": {
    "receipt_id": "RECEIPT-...",
    "case_id": "SECOM-0116",
    "handoff_status": "APPROVED"
  }
}
```

Errors: `404 CASE_NOT_FOUND`, `404 RECEIPT_NOT_FOUND`

Receipt는 법적 인증서, 실제 물류 인계 확인 또는 불변 감사 원장이 아닙니다.

## 12. Demo API

### `POST /api/v1/demo/reset`

Request body: 없음

- 로컬 시연 전용 `DEMO_MODE=true`와 `DEMO_RESET_ENABLED=true`가 모두 설정됐을 때만 활성화하며 reset flag 기본값은 `false`입니다.
- Golden Case `SECOM-0116`에 연결된 Workflow만 초기화하고 해당 Golden Case를 결정적으로 다시 seed합니다.
- 다른 Case와 공용 Demand는 보존합니다.
- REAL 출처의 Golden Detect 값은 같은 검증 산출물 값으로 복원합니다.
- 공개 배포에서는 비활성 기본을 유지하고, 비활성 상태에서는 404로 숨깁니다.
- `ENVIRONMENT=production`에서는 `SEED_DEMO_DATA` 또는 `DEMO_RESET_ENABLED`가 true이면 설정 검증에서 애플리케이션 시작 자체를 거부합니다.

Response `200`: 초기화된 Golden Case envelope
Errors: `404 NOT_FOUND`

## 13. Contract test 최소 목록

- 상세 응답의 7개 top-level key와 `snake_case`
- 미도달 단계 `null`
- 현장 확인 전 Passport 409
- `NOT_CONFIRMED` 종료와 이후 단계 차단
- top_k 1–3 검증과 Golden Top-3 순서
- Rule tri-state와 status 우선순위
- `REVIEW`가 아닌 후보 승인 거부
- APPROVED unknown quantity를 0으로 바꾸지 않음
- Scenario 재호출 동일 결과
- Receipt snapshot과 직전 Case 일치
- Match·Receipt 중복 요청 처리
- 모든 오류의 `trace_id`

## 14. 후속 TODO

- 운영 인증·조직·RBAC와 actor header 제거
- Pagination, 검색, 정렬
- 범용 idempotency request hash·처리 상태 저장
- 자유 Passport 입력을 처리하는 실제 BGE/Chroma Adapter 설정과 readiness
- OpenAPI example·frontend client 자동 생성
