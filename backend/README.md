# GreenFab Loop Backend

FastAPI, PostgreSQL, SQLAlchemy와 Alembic으로 구현한 GreenFab Loop MVP Backend입니다. Data Contract의 전체 Case 흐름을 저장하며, 기본 Golden snapshot과 선택 가능한 실제 BAAI/bge-m3·ChromaDB runtime을 제공합니다.

관련 문서:

- [Workflow](../docs/workflow.md)
- [API Contract](../docs/api-contract.md)
- [PostgreSQL Schema](../docs/backend-schema.md)
- [Data Contract v0.1](../docs/data-contract.md)
- [Golden Demo](../docs/demo-flow.md)
- [Backend Productization Foundations](../docs/backend-productization.md)
- [Render Backend Deployment](../docs/render-deployment.md)

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

GitHub의 `Backend CI` workflow는 Python 3.12와 PostgreSQL 16에서 다음 품질
게이트를 자동 실행합니다.

- core + storage + development dependency를 설치한 테스트와 Ruff 검사
- SHA-256으로 고정한 Render 공식 JSON Schema와 제품 안전 계약을 이용한 `render.yaml` 검증
- `upgrade -> check -> downgrade -> re-upgrade` migration 왕복 검증
- 기본 및 `match` profile의 Docker Compose 구성 검증
- 실행 중인 FastAPI/PostgreSQL을 통과하는 Golden Workflow smoke test

CI는 `MATCH_PROVIDER=mock`과 offline 환경을 강제하고 app coverage 85% 하한을 적용하며
`.[match]` extra를 설치하지 않습니다. 따라서 4.59GB BGE-M3 가중치를 내려받지 않습니다. 선택형 Chroma smoke는
로컬에서 `python -m pip install -e ".[dev,match]"` 후 다음처럼 별도로 실행합니다.

```bash
pytest -m requires_match_runtime
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
| `DATABASE_POOL_*` | `5 / 10 / 10초` | PostgreSQL connection pool 설정 |
| `SEED_DEMO_DATA` | `true` | 시작 시 Golden Case와 DEMO Demand upsert |
| `DEMO_MODE` | `true` | DEMO 기능 context |
| `DEMO_RESET_ENABLED` | `false` | 로컬 Golden reset 명시 활성화 |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | 허용 Frontend origin JSON array |
| `AUTH_MODE` | `demo` | 로컬 명시 Demo 또는 API key 필수 mode |
| `API_KEY_CREDENTIALS` | `[]` | 평문이 아닌 key SHA-256와 actor/role JSON |
| `EVIDENCE_STORAGE_BACKEND` | `local` | 로컬 개발은 filesystem, production은 `s3` 필수 |
| `EVIDENCE_S3_*` | `.env.example` 참고 | AWS S3/R2 등 S3-compatible private object storage |
| `EVIDENCE_S3_*_TIMEOUT_SECONDS`, `EVIDENCE_S3_MAX_ATTEMPTS` | `3 / 10 / 2` | object storage connect/read 상한과 총 시도 횟수 |
| `EVIDENCE_MAX_BYTES` | `5242880` | Evidence 최대 upload 크기 |
| `DETECT_ARTIFACT_MAX_BYTES` | `20971520` | Detect import artifact 최대 크기 |
| `MATCH_PROVIDER` | `mock` | `mock` 또는 명시적인 `bge_chroma`; 장애 시 자동 fallback 없음 |
| `BGE_MODEL_NAME`, `BGE_MODEL_REVISION` | `BAAI/bge-m3`, `5617a9f…` | embedding 모델과 고정 Hugging Face revision |
| `BGE_DEVICE` | `cpu` | CPU-first 실행 장치; CUDA는 명시 선택 |
| `BGE_BATCH_SIZE` | `4` | CPU 메모리를 고려한 보수적인 embedding batch |
| `MATCH_MAX_CONCURRENCY` | `1` | 프로세스당 동시 BGE inference 상한 |
| `MATCH_QUEUE_TIMEOUT_SECONDS` | `30` | inference slot 대기 상한; 초과 시 503 |
| `MATCH_PENDING_TIMEOUT_SECONDS` | `120` | crash 후 PENDING Match lease를 회수할 최소 시간 |
| `MATCH_RULE_POLICY_KEY` | `match-deterministic-v0` | v0.1 고정 reserved policy; 다른 값은 시작 거부 |
| `CHROMA_MODE` | `persistent` | embedded persistent client 또는 `http` server |
| `CHROMA_*` | `.env.example` 참고 | collection, 경로 또는 HTTP 연결 설정 |
| `DEMAND_INDEX_SYNC_ON_STARTUP` | `true` | BGE Provider 시작 시 PostgreSQL과 Chroma를 증분 reconcile |
| `POSTGRES_*` | `.env.example` 참고 | Compose PostgreSQL 설정 |

`DEMO_RESET_ENABLED`는 보안상 기본 `false`입니다. 공개 배포에서는 활성화하지 않습니다. 로컬 시연에서만 `DEMO_MODE=true`를 유지하고 `.env`를 다음처럼 바꾼 뒤 Backend를 재시작합니다.

```text
DEMO_RESET_ENABLED=true
```

Reset은 `SECOM-0116`에 연결된 Workflow만 초기화하고 다른 Case와 공용 Demand는 보존합니다. DEMO Demand 원복 뒤 BGE Provider의 전체 index sync를 실행하며, 실패는 DB event에 남기고 `503`으로 알립니다.

`ENVIRONMENT`가 `development`, `test`, `local` 외 값이면 다음 세 값을 모두 false로 설정해야
합니다. 하나라도 true이면 설정 검증에서 서버 시작을 거부합니다.

```text
DEMO_MODE=false
SEED_DEMO_DATA=false
DEMO_RESET_ENABLED=false
```

또한 Production은 `AUTH_MODE=required`와 하나 이상의 hash 기반
`API_KEY_CREDENTIALS`가 필요합니다. 자세한 role과 설정은
[`backend-productization.md`](../docs/backend-productization.md)를 참고합니다.
Production은 Render 같은 ephemeral filesystem에 Evidence를 남기지 않도록
`EVIDENCE_STORAGE_BACKEND=s3`도 강제합니다. S3 runtime을 선택하는 설치는
`python -m pip install -e ".[storage]"`이며 bucket/endpoint/credential은 환경변수로만
주입합니다. production의 custom endpoint는 HTTPS만 허용하며, 시작 시 bucket과 지정 prefix에
대한 list/head 및 임시 object put/get/delete 권한을 실제로 점검합니다. 업로드 object I/O는
Case row lock과 DB transaction 밖에서 실행하고, metadata commit 실패 시 생성 object를
best-effort로 제거합니다. 다운로드는 저장된 크기와 SHA-256을 전부 확인한 뒤에만 전송하며
private/no-store와 `nosniff` header를 반환합니다.

### Detect artifact Import

```bash
python -m app.cli.import_detect ../data/outputs/detect/dashboard_data.json \
  --source-type REAL \
  --actor pipeline_operator
```

같은 byte hash의 artifact를 재실행해도 import와 Case Audit를 중복 생성하지 않습니다.

### 실제 BGE-M3·ChromaDB 실행

Core 설치는 대형 ML package나 모델을 받지 않습니다. 실제 Provider를 선택할 때만 optional
extra를 설치합니다. Linux/Render CPU 배포에서는 일반 PyPI의 torch가 CUDA/NVIDIA package를
함께 선택하지 않도록 공식 PyTorch CPU wheel index를 사용하는 설치 script를 먼저 실행합니다.

```bash
bash scripts/install_match_runtime.sh
python -m pip install -e ".[dev]"
```

script는 torch 2.7.1 CPU wheel을 설치한 뒤 match/storage extras를 설치하고
`torch.version.cuda is None`과 dependency consistency를 검사합니다. Render는 Python
3.12.11로 고정하며, 공식 CPU index에 CPython 3.12용 Linux x86_64/aarch64 wheel이 모두
있는 것을 확인했습니다. 실제 Render build log에서 이 검사가 성공하기 전에는 CUDA package
제거가 검증됐다고 간주하지 않습니다.

embedded persistent Chroma를 사용할 때 `.env`를 다음처럼 설정합니다.

```text
MATCH_PROVIDER=bge_chroma
BGE_MODEL_NAME=BAAI/bge-m3
BGE_MODEL_REVISION=5617a9f61b028005a4858fdac845db406aefb181
BGE_DEVICE=cpu
BGE_BATCH_SIZE=4
CHROMA_MODE=persistent
CHROMA_PERSIST_DIRECTORY=.data/chroma
```

별도 Chroma HTTP server를 Compose로 실행하려면 다음 값을 `.env`에 적용하고 `match` profile을 시작합니다.

```text
INSTALL_MATCH_RUNTIME=true
MATCH_PROVIDER=bge_chroma
CHROMA_MODE=http
CHROMA_HOST=chroma
CHROMA_PORT=8000
```

Compose의 Chroma 서비스는 host port를 발행하지 않고 Compose 내부 네트워크에서 Backend만 접근합니다. 인증과 TLS를 별도로 구성하기 전에는 Chroma port를 외부 네트워크에 공개하지 않습니다. 기본 모델 revision은 [BAAI/bge-m3의 검증된 commit](https://huggingface.co/BAAI/bge-m3/commit/5617a9f61b028005a4858fdac845db406aefb181)으로 고정하며, revision을 바꾸면 별도 collection으로 재색인해야 합니다.

```bash
docker compose --profile match up --build
```

BGE 환경에서는 시작 시 모델을 한 번 로드하고 PostgreSQL 활성 Demand의 version/content hash를
Chroma metadata와 비교해 변경·누락된 문서만 upsert하고 stale ID를 삭제합니다. crash로 남은
PENDING index event는 시작 시 FAILED로 전환한 뒤 새 SYNC_ALL event로 reconcile합니다. 모델 또는
Chroma 준비가 실패하면 애플리케이션 시작/readiness가 실패하며 Mock으로 전환하지 않습니다.
BAAI 공식 모델 카드 기준 bge-m3는 약 567M parameters/4.59GB 규모이므로 모델 파일 외에도 추론 메모리 여유가 필요합니다. Core image에는 포함하지 않고 optional extra로만 설치하며 CPU 기본 batch를 4로 제한합니다. 문서 임베딩과 query 임베딩은 L2 normalize하고 Chroma cosine distance `d`는 `1 - d`로 similarity에 변환합니다. 이 점수는 적합도나 성공확률이 아닙니다.
Compose의 `greenfab_model_cache` volume은 첫 모델 다운로드를 재사용하고 `greenfab_chroma_data`는 embedded index를 보존합니다.

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
Golden signature가 없는 자유 입력은 고정 R01 점수를 재사용하지 않고 `503 MATCH_UNAVAILABLE`로 거부합니다.

`MATCH_PROVIDER=bge_chroma`는 실제 `BgeM3ChromaAdapter`를 선택합니다.

- BGE-M3는 고정 revision으로 프로세스 시작 시 한 번 로드
- CPU 기본, CUDA 명시 선택
- PostgreSQL 활성 Demand를 `demand_id`로 ChromaDB upsert하고 비활성 ID는 삭제
- Chroma에는 검색 문서, `demand_id`, version/hash metadata만 저장하고, 후보·Rule 필드는 PostgreSQL에서 읽은 뒤 MatchCandidate snapshot으로 고정
- stale vector ID를 고려해 overfetch한 뒤 활성 PostgreSQL 후보 Top-3만 사용
- 동일한 deterministic Rule Service 재사용
- Passport 또는 검색된 Demand 중 하나라도 `DEMO`이면 Match `source_type`도 `DEMO`
- 장애 시 Mock으로 조용히 전환하지 않고 `503 MATCH_UNAVAILABLE`

Demand 관리 API:

```text
GET  /api/v1/demands?include_inactive=false&limit=50&offset=0
POST /api/v1/demands
PUT  /api/v1/demands/{demand_id}
POST /api/v1/demands/{demand_id}/deactivate
POST /api/v1/demands/index/sync
GET  /api/v1/demands/index/events
```

읽기는 `VIEWER+`, create/update/deactivate/index sync와 event 조회는 `ADMIN`만 허용합니다. 이 경로들은 `X-Actor`를 무시하고 API principal actor만 기록합니다. 변경 transaction에 durable `demand_index_events`를 먼저 만들고, commit 후 Chroma를 동기화합니다. 실패하면 DB 변경은 보존되고 event가 `FAILED`가 되며 API는 `503 DEMAND_INDEX_UNAVAILABLE`를 반환합니다. 현재는 관리자가 전체 sync로 재처리하며 자동 worker는 후속 범위입니다.

Demand 목록도 `limit` 1~100, `offset`과 `X-Total-Count`/`X-Limit`/`X-Offset`
header를 지원합니다. 동일한 PUT 또는 이미 비활성인 Demand의 반복 deactivate는 version과
index event를 불필요하게 늘리지 않습니다.

## 7. 검증·무결성·동시성

- Pydantic이 문자열 앞뒤 공백을 제거하고 필수 문자열의 whitespace-only 입력을 거부합니다.
- Passport의 `quantity`와 `unit`은 API와 DB 모두에서 함께 존재하거나 함께 `null`이어야 합니다.
- Confirmation은 `PENDING`일 때 확인자·시각이 모두 `null`, 완료 상태일 때 비어 있지 않은 확인자·시각이 모두 존재해야 합니다.
- Workflow 변경은 PostgreSQL에서 해당 Case를 `SELECT ... FOR UPDATE`로 잠급니다. 단 Match는 짧은 prepare transaction에서 Passport·정책 revision과 PENDING run을 고정하고, BGE/Chroma inference는 lock/transaction 밖에서 수행한 뒤 persist transaction에서 snapshot을 다시 검증합니다.
- 명시적 Demo mode의 `X-Actor`는 공백 이외 문자를 포함한 1–120자만 허용합니다. Production actor는 API key principal에서 가져옵니다. `Idempotency-Key`는 공백 이외 문자를 포함한 1–255자만 허용합니다.
- `X-Trace-Id`는 trim 후 1–64자만 재사용하며 빈 값·초과 길이는 서버 UUID로 안전하게 대체합니다.
- Match/Receipt key 범위는 Case이므로 다른 Case에서 같은 문자열을 재사용할 수 있습니다. 같은 Case의 동시 재시도는 row lock과 DB 제약으로 한 건만 유지합니다.
- Decision → Match Candidate, Scenario → Decision, Receipt → Decision/Scenario lineage를 FK로 보존합니다.
- Match 도중 Passport 또는 Demand가 변경되면 PENDING run을 `FAILED`로 남기고 `409`로 재실행을 요구합니다. Candidate의 회사명·설명·Rule 입력·Demand version/hash는 snapshot이므로 이후 Demand 수정이 과거 결과를 바꾸지 않습니다.
- `APPROVED` 시 선택 Demand가 활성이고 Candidate snapshot과 같은 version/hash인지 다시 확인합니다.
- 존재하지 않는 경로와 잘못된 HTTP method까지 각각 `404 NOT_FOUND`, `405 METHOD_NOT_ALLOWED` 공통 오류 형식과 trace ID로 반환합니다.
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

- SSO/OIDC, 조직·사업장 tenant, DB-backed key rotation/revocation
- MES/QMS 또는 artifact registry에서 Detect artifact를 감지해 CLI를 자동 호출하는 scheduler/connector
- 범용 idempotency request hash·processing 상태
- PostgreSQL 기반 동시성·부하 테스트
- Demand index event 자동 재시도 worker와 backoff/metrics
- 실제 인계 증빙이 필요할 경우 별도 도메인·법적 검토
- Evidence malware scan, retention/deletion 및 orphan reconcile worker
- 실제 inference wall-clock timeout과 multi-worker 부하 제한
