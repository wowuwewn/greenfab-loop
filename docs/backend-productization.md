# Backend Productization Foundations

이 문서는 Productization 기반과 통합된 Match/Demand runtime을 설명합니다. 실제
법적 인계, 규제 적합성 또는 인증을 구현하거나 주장하지 않습니다.

## 1. Detect artifact 자동 Import

`ai/detect/run_pipeline.py`가 생성하는 contract-compatible `dashboard_data.json`을 Case로
적재합니다.

```bash
cd backend
alembic upgrade head
python -m app.cli.import_detect ../data/outputs/detect/dashboard_data.json \
  --source-type REAL \
  --actor pipeline_operator
```

필수 입력은 `metadata.dataset`, `summary.선정모델명`, 하나 이상의 `risk_items`입니다.
각 `risk_item`의 `id`, `risk_rank`, `risk_score`, `risk_score_type`, `top_factors`를 검증합니다.

- artifact byte SHA-256가 import idempotency key입니다.
- 같은 artifact 재실행은 `detect_imports`나 Audit Event를 중복 생성하지 않습니다.
- 새 Case에는 PENDING Resource Confirmation과 `CASE_IMPORTED_FROM_DETECT` Event를 만듭니다.
  Import만으로 실제 자원 확인을 주장하지 않으므로 이 초기 Confirmation은 `DEMO`입니다.
- 기존 Case는 Detect 필드만 갱신하고 진행 중인 Workflow와 사람 입력을 보존합니다.
- DB에는 절대 로컬 경로 대신 파일명, hash, dataset/model/validation metadata만 저장합니다.
- 같은 hash를 REAL과 DEMO처럼 서로 다른 `source_type`으로 등록하면 conflict입니다.
- artifact 크기는 `DETECT_ARTIFACT_MAX_BYTES`로 제한합니다.

`detect_imports`는 artifact provenance이고 `cases.detect_import_id`가 현재 Case 결과를 해당
import에 연결합니다. `model_revision`은 실제 모델 registry revision이 없을 때 artifact SHA-256를
사용합니다. Detect artifact 자동 polling이나 MES/QMS connector는 아직 포함하지 않습니다.

## 2. API key 인증과 역할

`AUTH_MODE`는 다음 두 값만 허용합니다.

- `demo`: `ENVIRONMENT=development|test|local`이고 `DEMO_MODE=true`일 때만 허용합니다.
  `X-Actor` 또는 `DEMO_ACTOR`를 사용하며 모든 권한을 가진 명시적 DEMO principal입니다.
- `required`: `X-API-Key`가 필수입니다. Production은 반드시 이 mode이고 demo seed/reset은
  비활성화해야 합니다. `development|test|local` 외 환경은 `DEMO_MODE`도 false여야 합니다.

평문 API key는 설정에 저장하지 않습니다. SHA-256 digest를 생성해 환경변수로 주입합니다.
원본 key는 최소 16자이며 `secrets.token_urlsafe(32)`처럼 충분한 entropy로 생성해야 합니다.

```bash
python -c "import getpass, hashlib; print(hashlib.sha256(getpass.getpass().encode()).hexdigest())"
```

```text
AUTH_MODE=required
API_KEY_CREDENTIALS=[{"key_id":"factory-admin","secret_sha256":"<64-hex>","actor":"factory_admin","role":"ADMIN"}]
```

Role hierarchy:

| Role | 권한 |
| --- | --- |
| `VIEWER` | Case, Receipt, Evidence metadata/content, Rule catalog, Demand 조회 |
| `OPERATOR` | VIEWER + Confirm, Passport, Evidence upload, Match, Scenario |
| `DECISION_MAKER` | OPERATOR + Decision, Receipt 생성 |
| `ADMIN` | 전체 + Demand 변경/index 관리, Rule policy version/activation, 활성화된 Demo reset |

`required` mode에서는 `confirmed_by`, `decided_by`, `X-Actor`를 신뢰하지 않고 API key에 연결된
actor를 저장합니다. 이 인증은 최소 경계이며 tenant, SSO/OIDC, key rotation UI, DB-backed key
revocation은 후속 범위입니다.

## 3. Passport Evidence

지원 API:

```text
POST /api/v1/cases/{case_id}/resource-passport/evidence
GET  /api/v1/cases/{case_id}/resource-passport/evidence
GET  /api/v1/cases/{case_id}/resource-passport/evidence/{evidence_id}/content
```

Upload는 `multipart/form-data`입니다.

```bash
curl -X POST http://localhost:8000/api/v1/cases/SECOM-0116/resource-passport/evidence \
  -H 'X-API-Key: <secret>' \
  -F 'evidence_type=ANALYSIS_REPORT' \
  -F 'description=성분 분석 원본' \
  -F 'file=@report.pdf;type=application/pdf'
```

- 허용 형식: PDF, JPEG, PNG
- 기본 최대 크기: 5 MiB (`EVIDENCE_MAX_BYTES`)
- 선언 Content-Type과 PDF/JPEG/PNG signature를 함께 검사합니다.
- 사용자 filename은 metadata로만 보존하며 storage path에는 UUID key만 사용합니다.
- API 응답은 local storage path/key를 노출하지 않고 size, SHA-256, type, actor를 반환합니다.
- Evidence `source_type`은 인증 mode가 아니라 연결된 Passport의 출처를 상속합니다.
- Upload는 Passport 저장 후 Decision 전인 `PASSPORT_READY`, `MATCH_READY`에서만 허용합니다.
- Evidence 추가는 Workflow 상태를 바꾸지 않고 Audit Event를 남깁니다.
- Demo reset은 Golden Case의 local evidence 파일도 best-effort로 제거하고 실패를 서버 log에 남깁니다.
- Object 저장은 DB transaction과 Case row lock 밖에서 수행하고 최종 attach 시 Workflow 상태를
  다시 검사합니다. attach 실패 시 저장 object를 best-effort로 보상 삭제합니다.
- Download는 metadata의 size와 SHA-256을 전부 검증한 뒤 전송하며 private/no-store와
  `X-Content-Type-Options: nosniff`를 반환합니다.

`LocalEvidenceStorage`는 로컬 개발 전용이며 production은 S3-compatible private storage를
강제합니다. 시작 시 bucket과 임시 object Put/Get/Delete 권한을 점검하고 bounded timeout/retry를
사용합니다. 운영 전에는 malware scan, encryption/KMS, retention/deletion 및 orphan reconcile
job을 구성해야 합니다.
애플리케이션 저장 제한과 별개로 ingress/reverse proxy에도 multipart body 제한을 설정해야 합니다.
첨부는 사실 자료일 뿐 법적 검증이나 인계 증명이 아닙니다.

## 4. Versioned Rule policy catalog

정책 catalog와 deterministic evaluator lineage를 분리해 추적합니다.

```text
GET  /api/v1/rule-policies
GET  /api/v1/rule-policies/{policy_key}
POST /api/v1/rule-policies/{policy_key}/versions
POST /api/v1/rule-policies/{policy_key}/versions/{version}/activate
```

지원 field는 `description`, `quantity`, `unit`, `condition`, `location`, `composition`이며 operator는
`REQUIRED`, `GTE`, `LTE`, `EQUALS`, `IN`입니다. Version definition은 canonical JSON SHA-256,
creator, activation actor/time과 함께 immutable row로 저장됩니다. 활성 version 변경은 기존
version을 수정하지 않습니다.

Match prepare 시 v0.1 고정 `MATCH_RULE_POLICY_KEY=match-deterministic-v0`의 active revision을 resolve하고 `policy_key`, `version`, `definition_sha256`를 MatchRun과 Audit/Receipt envelope에 고정합니다. 다른 key override는 신뢰할 provisioning 경로가 없으므로 설정 검증에서 서버 시작을 거부합니다. 이 reserved policy는 현재 evaluator가 수량·단위, 필수정보, 위치만 검사한다는 실행 계약을 추적하며 API 변경을 금지합니다. Demand별 실제 조건은 Candidate snapshot에 별도로 저장하며, policy catalog를 법규·안전성 판정으로 설명하면 안 됩니다. `accepted_conditions`는 검색 문서 보강용이고 hard Rule이 아닙니다.

reserved policy version 1은 demo seed가 아니라 `0003_demand_runtime` data migration이 설치하므로
`SEED_DEMO_DATA=false`인 Production에서도 Match가 동작합니다. Application seed는 create-all 기반
로컬 테스트를 위해 같은 stable ID/hash를 idempotent하게 보장합니다.

## 5. Case 검색과 Pagination

기존 배열 응답 호환성을 유지하면서 query와 header를 추가했습니다.

```text
GET /api/v1/cases?search=SECOM&workflow_status=MATCH_READY&limit=50&offset=0
```

- `limit`: 1~100, 기본 50
- `offset`: 0 이상
- `search`: Case ID 대소문자를 구분하지 않는 literal substring 검색
- `workflow_status`: 내부 Workflow enum
- 응답 header: `X-Total-Count`, `X-Limit`, `X-Offset`

CORS에서 위 header와 `X-Trace-Id`를 Frontend에 노출합니다.

Demand 목록도 `include_inactive`, `limit`(1~100), `offset`을 지원하고 동일한 세 pagination
header를 반환합니다. 내용이 같은 PUT과 이미 비활성인 Demand의 반복 deactivate는 version이나
index event를 새로 만들지 않습니다.

## 6. 운영 설정과 Health

- PostgreSQL pool: `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`,
  `DATABASE_POOL_TIMEOUT_SECONDS`
- `/health/live`: process liveness만 확인
- `/health/ready`: DB `SELECT 1`, Match provider class, Evidence storage 접근 가능 여부 확인
- 공통 오류 shape에 401, 403, 413을 추가
- `MATCH_PENDING_TIMEOUT_SECONDS`: 기본 120초, crash로 남은 PENDING Match lease 회수 기준

실제 BGE/Chroma provider readiness와 Evidence storage deep probe가 포함됩니다. 외부 플랫폼의
자동 restart probe는 `/health/live`를 사용하고 `/health/ready`는 수동·외부 deep check로
모니터링합니다. rate limit, SSO, backup과 observability는 별도 운영 작업입니다.

## 7. Migration

`0002_productization_foundations`가 다음을 추가합니다.

- `detect_imports`
- `cases.detect_import_id`, `risk_score`, `risk_score_type`
- `passport_evidence`
- `rule_policies`, `rule_policy_versions`

`0003_demand_runtime`은 Demand lifecycle/version/hash, target revision을 가진 durable index event,
Match input/policy lineage, execution token, Candidate snapshot과 reserved evaluator policy data를
추가합니다.

SQLite upgrade/downgrade·schema drift, PostgreSQL offline DDL, 로컬 Docker PostgreSQL 16의
upgrade와 `alembic check`를 검증했습니다. 운영 적용 전에는 실제 관리형 PostgreSQL 환경에서
upgrade/downgrade와 lock behavior를 다시 확인해야 합니다.
