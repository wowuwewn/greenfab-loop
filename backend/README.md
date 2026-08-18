# GreenFab Loop Backend

FastAPI, PostgreSQL, SQLAlchemy와 Alembic으로 구현한 GreenFab Loop MVP Backend입니다. Data Contract의 전체 Case 흐름을 저장하고, 고정 DEMO Match snapshot을 통해 프런트 E2E 개발과 Golden Demo를 지원합니다.

관련 문서:

- [Workflow](../docs/workflow.md)
- [API Contract](../docs/api-contract.md)
- [PostgreSQL Schema](../docs/backend-schema.md)
- [Data Contract v0.1](../docs/data-contract.md)
- [Golden Demo](../docs/demo-flow.md)

## 1. Docker Compose로 시작

요구사항: Docker와 Docker Compose

```bash
cd backend
cp .env.example .env
docker compose up --build
```

`.env`의 기본 예시 비밀번호는 로컬 개발 전용입니다. 공개 환경에서는 반드시 변경합니다. Backend container는 PostgreSQL healthcheck가 성공하면 `alembic upgrade head`를 실행한 뒤 API를 시작합니다.

접속 주소:

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Live health: [http://localhost:8000/health/live](http://localhost:8000/health/live)
- Ready health: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

종료:

```bash
docker compose down
```

위 명령은 PostgreSQL named volume을 유지합니다.

## 2. 로컬 Python 실행

요구사항: Python 3.11 이상, 실행 중인 PostgreSQL

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`.env`의 `DATABASE_URL`과 Compose의 `POSTGRES_*` 값이 일치해야 합니다.

## 3. 검사 명령

테스트는 in-memory SQLite type variant를 사용해 빠르게 실행됩니다. PostgreSQL migration은 Docker Compose로 별도 확인합니다.

```bash
cd backend
source .venv/bin/activate
pytest
ruff check .
ruff format --check .
alembic upgrade head
alembic current
```

새 schema 변경은 모델과 migration을 함께 수정합니다.

```bash
alembic revision --autogenerate -m "describe change"
```

생성된 migration은 반드시 직접 검토합니다.

## 4. 환경변수

| 변수 | 기본·예시 | 설명 |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL URL | SQLAlchemy/psycopg 연결 문자열 |
| `DATABASE_ECHO` | `false` | SQL log 출력 |
| `SEED_DEMO_DATA` | `true` | 시작 시 Golden Case와 DEMO Demand upsert |
| `DEMO_MODE` | `true` | DEMO 기능 context |
| `DEMO_RESET_ENABLED` | `false` | 로컬 Golden reset 명시 활성화 |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | 허용 Frontend origin JSON array |
| `POSTGRES_*` | `.env.example` 참고 | Compose PostgreSQL 설정 |

`DEMO_RESET_ENABLED`는 보안상 기본 `false`입니다. 공개 배포에서는 활성화하지 않습니다. 로컬 시연에서만 `DEMO_MODE=true`를 유지하고 `.env`를 다음처럼 바꾼 뒤 Backend를 재시작합니다.

```text
DEMO_RESET_ENABLED=true
```

Reset은 `SECOM-0116`에 연결된 Workflow만 초기화하고 다른 Case와 공용 Demand는 보존합니다.

`ENVIRONMENT=production`에서는 다음 두 값을 모두 false로 설정해야 합니다. 하나라도 true이면 설정 검증에서 서버 시작을 거부합니다.

```text
SEED_DEMO_DATA=false
DEMO_RESET_ENABLED=false
```

## 5. Golden Case API 순서

기본 Golden Case는 `SECOM-0116`입니다.

### 1) 초기 상태 조회

```bash
curl http://localhost:8000/api/v1/cases/SECOM-0116
```

### 2) 사람이 Resource 발생 확인

```bash
curl -X PUT http://localhost:8000/api/v1/cases/SECOM-0116/resource-confirmation \
  -H 'Content-Type: application/json' \
  -d '{"status":"CONFIRMED","confirmed_by":"demo_operator"}'
```

### 3) DEMO Resource Passport 저장

```bash
curl -X PUT http://localhost:8000/api/v1/cases/SECOM-0116/resource-passport \
  -H 'Content-Type: application/json' \
  -H 'X-Actor: demo_operator' \
  -d '{"description":"반도체 세정 공정에서 회수된 DEMO 미세 무기질 분말","quantity":12,"unit":"kg","condition":"건조 분말","location":"제조동 A","composition":"이산화규소 중심 합성 DEMO 성분표"}'
```

### 4) Top-3 Match와 Rule 실행

```bash
curl -X POST http://localhost:8000/api/v1/cases/SECOM-0116/matches \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: golden-match-v1' \
  -d '{"top_k":3}'
```

### 5) 사람이 최종 Decision 저장

```bash
curl -X PUT http://localhost:8000/api/v1/cases/SECOM-0116/decision \
  -H 'Content-Type: application/json' \
  -d '{"status":"APPROVED","selected_demand_id":"D01","reason":"성분 분석 완료 후 파일럿 검토를 진행합니다.","decided_by":"demo_manager"}'
```

`APPROVED`는 최신 Match의 `REVIEW` 후보만 허용합니다. 현재 MVP에는 Rule override가 없습니다.
Backend는 외부 `selected_demand_id`와 함께 내부 `selected_match_candidate_id` FK를 저장해 실제 검토 후보를 추적합니다.

### 6) 후보 전환량 Scenario 생성

```bash
curl -X POST http://localhost:8000/api/v1/cases/SECOM-0116/esg-scenario
```

### 7) Green Receipt 생성·조회

```bash
curl -X POST http://localhost:8000/api/v1/cases/SECOM-0116/receipt \
  -H 'Idempotency-Key: golden-receipt-v1'

curl http://localhost:8000/api/v1/cases/SECOM-0116/receipt
```

Receipt 조회는 생성 시 저장된 전체 `CaseEnvelope` snapshot을 반환합니다.
Scenario는 `decision_id`, Receipt는 `decision_id`와 `scenario_id` FK를 저장해 계산·기록 lineage를 보존합니다.

### 로컬 Demo reset

`DEMO_MODE=true`와 `DEMO_RESET_ENABLED=true`일 때만 실행됩니다. 공개 배포와 production에서는 비활성 상태를 유지합니다.

```bash
curl -X POST http://localhost:8000/api/v1/demo/reset
```

## 6. Match Provider 경계

Workflow Service는 구체적인 embedding 구현이 아니라 `MatchProvider` protocol에 의존합니다.

```text
MatchProvider.match(passport, top_k) -> MatchResult
```

현재 `MockMatchProvider`는 다음 특성을 가집니다.

- 네트워크, CUDA, 모델 다운로드, ChromaDB 없이 동작
- BGE-M3로 사전 생성한 Golden R01 전용 `greenfab-loop-synthetic-v1@2026-08-16` 고정 DEMO snapshot
- `Xenova/bge-m3` 모델명과 사전 생성된 고정 유사도 점수
- 같은 Passport 입력에 반복 가능한 후보·Rule 결과
- Passport `description`에 `반도체`, `세정`, `무기질` 세 signature가 모두 있는 Golden 입력만 허용

고정 점수는 현재 요청의 runtime 추론값이 아니며 실제 산업 적합성, 안전성 또는 재활용 성공확률이 아닙니다.
API의 `match.created_at`은 고정 snapshot 생성시각이 아니라 현재 Match Run이 완료된 시각입니다. snapshot ID는 내부 `model_revision`으로 별도 저장합니다.
Golden signature가 없는 자유 입력은 고정 R01 점수를 재사용하지 않고 `503 MATCH_UNAVAILABLE`로 거부합니다. 자유 입력 검색에는 실제 BGE-M3/ChromaDB Adapter가 필요합니다.

실제 BGE-M3/ChromaDB 연동은 `SemanticSearchAdapter`를 구현해 교체합니다.

- BGE-M3는 프로세스 시작 시 한 번 로드
- CPU 기본, CUDA 명시 선택
- PostgreSQL Demand를 `demand_id`로 ChromaDB upsert
- 검색 ID를 PostgreSQL Demand와 조인
- 동일한 deterministic Rule Service 재사용
- 장애 시 Mock으로 조용히 전환하지 않고 `503 MATCH_UNAVAILABLE`

현재 PR에는 실제 BGE/Chroma Adapter와 Provider 선택 환경변수가 포함되지 않습니다.

## 7. 검증·무결성·동시성

- Pydantic이 문자열 앞뒤 공백을 제거하고 필수 문자열의 whitespace-only 입력을 거부합니다.
- Passport의 `quantity`와 `unit`은 API와 DB 모두에서 함께 존재하거나 함께 `null`이어야 합니다.
- Confirmation은 `PENDING`일 때 확인자·시각이 모두 `null`, 완료 상태일 때 비어 있지 않은 확인자·시각이 모두 존재해야 합니다.
- 모든 Workflow 변경은 PostgreSQL에서 해당 Case를 `SELECT ... FOR UPDATE`로 잠근 뒤 실행합니다.
- `X-Actor`는 공백 이외 문자를 포함한 1–120자, `Idempotency-Key`는 공백 이외 문자를 포함한 1–255자만 허용합니다.
- `X-Trace-Id`는 trim 후 1–64자만 재사용하며 빈 값·초과 길이는 서버 UUID로 안전하게 대체합니다.
- Match/Receipt key 범위는 Case이므로 다른 Case에서 같은 문자열을 재사용할 수 있습니다. 같은 Case의 동시 재시도는 row lock과 DB 제약으로 한 건만 유지합니다.
- Decision → Match Candidate, Scenario → Decision, Receipt → Decision/Scenario lineage를 FK로 보존합니다.
- Match, Decision, Scenario, Receipt 저장은 각각 하나의 DB transaction으로 처리합니다.
- DB 장애는 `503 DATABASE_UNAVAILABLE`, Match Provider 장애는 `503 MATCH_UNAVAILABLE`, 예상하지 못한 예외는 stack trace를 숨긴 `500 INTERNAL_ERROR` 공통 형식으로 반환합니다.

## 8. 데이터·표현 한계

- `SECOM-0116`의 Detect·SHAP은 실제 Detect artifact를 바탕으로 한 `REAL` 데이터입니다.
- Resource 확인, Passport, Demand, Match와 사용자 정보는 해커톤 `DEMO` 데이터입니다.
- SHAP은 예측 기여도이며 원인·인과관계가 아닙니다.
- semantic similarity는 의미 유사도이며 적합도·안전성·성공확률이 아닙니다.
- ESG는 `candidate_diversion_quantity`만 계산하는 `SCENARIO`입니다. 탄소 감축량이나 실제 전환 실적이 아닙니다.
- 승인 수량을 모르면 후보 전환량도 `null`이며 unknown을 0으로 바꾸지 않습니다.
- Green Receipt는 내부 의사결정 snapshot입니다. 법적 인증서, 실제 인계 증명 또는 암호학적 불변 원장이 아닙니다.
- MVP에서는 `HANDOFF_CONFIRMED`를 생성하지 않습니다.

## 9. 후속 TODO

- 인증·조직·RBAC와 actor를 인증 context에서 주입
- 자유 Passport 입력을 처리하는 실제 BGE-M3/ChromaDB Adapter와 readiness probe
- Detect artifact 자동 import
- 범용 idempotency request hash·processing 상태
- PostgreSQL 기반 동시성·부하 테스트
- 실제 인계 증빙이 필요할 경우 별도 도메인·법적 검토
