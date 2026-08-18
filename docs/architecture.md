# GreenFab Loop MVP Architecture

## 1. 문서 목적

이 문서는 GreenFab Loop 해커톤 MVP의 실행 구조, 모듈별 책임, 데이터 저장 경계와 장애 처리 원칙을 정의합니다. 외부 JSON의 필드명과 의미는 [`data-contract.md`](./data-contract.md)를 우선하며, 이 문서는 해당 계약을 변경하지 않습니다.

핵심 원칙은 다음과 같습니다.

- 위험 탐지, 의미 유사도 검색, 규칙 검사와 사람의 최종 결정을 서로 분리합니다.
- PostgreSQL을 업무 상태의 단일 기준점(source of truth)으로 사용합니다.
- ChromaDB는 수요 후보의 벡터 검색에만 사용하며 업무 상태를 저장하지 않습니다.
- 데이터 출처는 `REAL`, `DEMO`, `SCENARIO`로만 구분합니다.
- AI는 `APPROVED`, `HOLD`, `REJECTED`를 결정하지 않습니다.
- Green Receipt는 내부 의사결정 스냅샷이며 법적 인증서, 불변 감사 원장 또는 실제 인계 증명이 아닙니다.

## 2. 논리 구조

```mermaid
flowchart LR
    U["현장·환경/자원 담당자"] --> F["Vite / React Frontend"]
    F -->|"JSON over HTTP /api/v1"| A["API Key / Role Boundary"]
    A --> B["FastAPI Backend"]

    B --> W["Workflow Service"]
    W --> P[("PostgreSQL")]
    W --> D["Detect Seed / Adapter"]
    W --> M["Match Provider"]
    W --> R["Deterministic Rule Service"]
    W --> S["Scenario Service"]
    W --> G["Receipt Service"]
    W --> E["Passport Evidence Service"]
    E --> L[("Local dev storage\nFuture object storage")]

    DP["Offline Detect Pipeline\nLightGBM · OOF · SHAP"] --> O["dashboard_data.json"]
    O --> D
    D --> P

    M --> MM["MockMatchProvider"]
    M --> BM["Optional BGE/Chroma Runtime\nBAAI/bge-m3"]
    BM --> C[("ChromaDB\nDemand vectors")]
    BM --> P
    R --> P
```

## 3. 구성 요소별 책임

| 구성 요소 | 책임 | 하지 않는 일 |
| --- | --- | --- |
| Frontend | Case 조회, 사용자 입력, 단계별 결과 표시, 오류·재시도 UX | 상태 전이 우회, AI 판단 생성, 브라우저 메모리를 최종 저장소로 사용 |
| FastAPI | API, 입력 검증, 트랜잭션, 상태 전이, Provider 호출, 응답 조립 | 요청마다 Detect 모델 학습, 의미 유사도를 최종 적합성으로 해석 |
| PostgreSQL | Case, Detect provenance, 확인, Passport/Evidence metadata, Demand, Match, Decision, Scenario, Receipt, Audit, Rule policy 저장 | 벡터 최근접 검색, evidence binary 저장 |
| Offline Detect | 동일 Fold 모델 비교, LightGBM/OOF/SHAP 결과 생성 | Resource·폐기물·재활용 정보를 추론 |
| Detect Import | 검증된 Detect 산출물을 hash 기반으로 idempotent Case upsert | 원본 결과에 공정 의미를 임의 부여, 기존 Workflow 초기화 |
| BGE-M3 / ChromaDB | Passport 텍스트와 활성 Demand 텍스트의 Top-k 의미 유사도 검색 | 안전성·성공확률·실제 산업 적합성 판단 |
| Rule Service | 수량, 필수정보, 위치 등 명시적 조건의 결정론적 검사 | LLM 기반 조건 생성, 최종 승인·거절 |
| Human Decision | 후보 선택과 `APPROVED`, `HOLD`, `REJECTED` 입력 | AI가 대신 수행할 수 없음 |
| Scenario Service | 사용자 입력 수량·경로·선택 계수를 명시된 수식으로 재계산·저장 | 검증되지 않은 계수 생성, 실제 탄소 감축량이나 전환 실적 주장 |
| Receipt Service | 생성 시점의 전체 Case를 JSONB 스냅샷으로 기록 | 실제 물류 인계 확인, 법적 인증서 발행 |

## 4. 실행 파이프라인

1. Offline Detect Pipeline이 실제 SECOM 입력으로 위험 순위와 SHAP 결과를 생성합니다.
2. Golden seed 또는 Detect CLI가 검증 산출물을 `case`와 provenance 형식으로 PostgreSQL에 적재합니다.
3. 사람이 실제 Resource 발생 여부를 `CONFIRMED` 또는 `NOT_CONFIRMED`로 입력합니다.
4. `CONFIRMED`인 경우에만 DEMO Resource Passport를 저장합니다.
5. Backend가 Passport를 현재 설정된 Match Provider에 전달합니다.
6. Match Provider가 후보를 반환하고 Rule Service가 명시적 조건을 검사합니다.
7. Backend가 짧은 persist transaction에서 입력 snapshot을 재검증하고 Match 후보를 저장합니다.
8. 사람이 후보와 근거를 확인한 뒤 최종 Decision을 입력합니다.
9. Scenario Service가 사용자 입력 수량·경로·선택 계수를 `ESG-SCENARIO-v0.1`로 재계산해 저장합니다.
10. Receipt Service가 전체 결정 상태를 스냅샷으로 저장합니다.

상세 상태 전이는 [`workflow.md`](./workflow.md), API 요청·응답은 [`api-contract.md`](./api-contract.md), 관계형 스키마는 [`backend-schema.md`](./backend-schema.md)를 따릅니다.

## 5. Match Provider 경계

Backend는 Match 구현에 직접 의존하지 않고 동일한 인터페이스를 사용합니다.

```text
MatchProvider.match(passport, top_k) -> MatchResult
├─ MockMatchProvider
└─ BgeChromaMatchProvider -> BgeM3ChromaAdapter
```

### `MockMatchProvider`

- 백엔드와 프런트의 E2E 개발, 반복 가능한 Golden Demo에 사용합니다.
- BGE-M3로 사전 생성한 `greenfab-loop-synthetic-v1@2026-08-16` 고정 DEMO Top-3 snapshot을 결정적인 순서로 반환합니다.
- 저장된 점수는 runtime 추론값이 아니라 사전 생성된 snapshot 값이며 `model`, `model_revision`으로 출처를 구분합니다. 외부 `match.created_at`은 snapshot 생성시각이 아니라 현재 Match Run의 완료 시각입니다.
- 고정 snapshot을 실제 산업 적합성·안전성·재활용 성공확률로 해석하지 않습니다.

### `BgeChromaMatchProvider`

- `MATCH_PROVIDER=bge_chroma`로 명시적으로 선택합니다.
- optional `match` dependency를 설치한 프로세스에서 고정 revision의 BGE-M3 모델을 한 번 로드합니다.
- CPU가 기본이며 `BGE_DEVICE`로 다른 장치를 명시할 수 있습니다.
- 공식 모델 카드 기준 약 567M parameters/4.59GB 모델이므로 core image에 포함하지 않고 CPU 기본 batch를 4로 제한합니다.
- PostgreSQL의 활성 Demand를 `demand_id` 기준으로 ChromaDB에 upsert하고 비활성 ID는 삭제합니다.
- vector metadata의 Demand version/hash가 PostgreSQL과 다르면 stale hit를 버립니다.
- version/hash가 없는 legacy hit도 현재 Demand에 wildcard로 결합하지 않고 제외합니다.
- 비어 있고 lineage metadata가 없는 legacy collection은 cosine/model/revision metadata로 안전하게 재생성하며, 데이터가 있는 legacy collection은 재색인을 요구하며 시작을 거부합니다.
- 실제 계산된 `semantic_similarity`와 Top-k 후보를 반환합니다.
- query/document embedding을 normalize하고 cosine distance `d`를 `1 - d` similarity로 변환합니다.
- Chroma hit의 ID를 PostgreSQL Demand와 다시 조인한 후 deterministic Rule을 실행합니다.
- stale ID를 고려해 overfetch하고 활성 PostgreSQL 후보 Top-3만 반환합니다.
- 모델은 lazy single load, CPU 기본, 프로세스당 concurrency 1 기본입니다.
- embedded 모델·collection 접근은 한 프로세스 안에서 Match와 index mutation 사이에 직렬화됩니다.
- embedded persistent client와 별도 HTTP Chroma server를 모두 지원합니다.

기본은 반복 가능한 `MockMatchProvider`입니다. BGE runtime을 선택한 뒤 모델·Chroma가 실패하면 시작/readiness 또는 Match가 실패하며 Mock으로 조용히 대체하지 않습니다. 테스트에서는 `create_app(match_provider=...)`로 fake Provider를 주입합니다.

## 6. 데이터 저장 경계

### PostgreSQL

- Workflow 상태와 모든 사용자 입력의 단일 기준점
- Match 실행 당시 모델명, 후보, Rule 결과 보관
- 사용자 Decision과 Audit Event 보관
- Scenario 입력·결과와 Receipt 스냅샷 보관
- Detect import hash/model provenance, Evidence metadata, versioned Rule policy 보관
- API 쓰기는 트랜잭션과 상태 검사를 통과해야 함

### ChromaDB

- 검색 가능한 Demand embedding과 최소 검색 metadata만 보관
- PostgreSQL의 `demand_id`를 document ID로 사용
- 중복 insert 대신 upsert
- Case, Decision, Receipt, Audit Event를 저장하지 않음
- ChromaDB를 지워도 PostgreSQL 원본에서 재구성 가능해야 함

### 파일 산출물

- Detect 학습·OOF·SHAP은 오프라인 산출물로 관리합니다.
- 현재 seed 값은 검증된 `dashboard_data.json` 산출물에서 복사한 값이며 API 요청 중 모델을 재학습하지 않습니다.
- CLI import는 artifact hash를 기준으로 Case를 upsert하고 기존 Workflow 진행 상태를 보존합니다.
- Evidence binary는 Git/DB에 넣지 않고 개발 환경의 generated-key local storage에 저장합니다.
- 원본 SECOM 데이터와 비밀값은 Git에 포함하지 않습니다.

## 7. 출처와 해석 경계

| 단계 | MVP `source_type` | 해석 경계 |
| --- | --- | --- |
| 실제 SECOM 기반 Detect | `REAL` | 위험 순위이며 불량 확률로 단정하지 않음 |
| SHAP | `REAL` | 예측 기여도이며 원인·인과관계가 아님 |
| DEMO 현장 확인·Passport·Demand | `DEMO` | 실제 제조 현장 정보로 주장하지 않음 |
| DEMO 입력 기반 BGE-M3 Match | `DEMO` | 실제 계산값이어도 입력 출처가 DEMO이므로 DEMO |
| ESG 사용자 입력·계산 결과 | `SCENARIO` | 가정 비교이며 실제 전환·감축 실적이 아님 |

`COMPUTED`, `HUMAN`, `LOCAL` 같은 값을 `source_type`에 추가하지 않습니다. 사람의 입력 여부와 저장 상태는 별도 필드와 Audit Event로 표현합니다.

## 8. 트랜잭션과 장애 처리

- 상태 변경 API는 SQLAlchemy transaction 안에서 대상 Case를 `SELECT ... FOR UPDATE`로 잠급니다. Match만 prepare→외부 inference→persist로 나뉘며 inference 중에는 transaction과 Case lock을 유지하지 않습니다.
- Match는 짧은 prepare transaction, transaction 없는 provider inference, 짧은 persist transaction으로 분리합니다. persist 전에 Case·Passport·Demand·Rule 입력 snapshot과 execution token을 다시 검증하고, Rule 결과와 aggregate source type은 잠근 PostgreSQL Demand와 Passport에서 서버가 다시 계산합니다.
- 잘못된 단계 요청은 `409 INVALID_STATE`로 거절합니다.
- Match와 Receipt는 선택적 `Idempotency-Key`를 지원하며 UI에서는 매번 전송하는 것을 권장합니다. Match의 오래된 PENDING lease는 새 execution token으로 안전하게 회수하고, 이전 inference 결과는 거부합니다.
- Scenario는 Case당 하나만 저장하고 재요청 시 같은 결과를 반환합니다.
- PostgreSQL 또는 Evidence storage 접근이 실패하면 deep readiness가 실패합니다. 외부 platform의
  restart probe는 process liveness만 보는 `/health/live`를 사용합니다. 응답은 주입된 Provider class 이름도 함께 표시합니다.
- 미완성 객체를 저장하고 성공 응답을 반환하지 않습니다.
- 모든 오류 응답에는 추적 가능한 `trace_id`를 포함합니다.
- 같은 Case와 같은 Demand의 동시 상태 전이는 PostgreSQL row lock으로 직렬화합니다. embedded BGE/Chroma index 연산은 현재 프로세스 안에서만 직렬화되므로 단일 API worker 배포를 사용해야 합니다. 다중 worker에는 PostgreSQL advisory lock 또는 전용 index worker가 필요합니다.

## 9. 실행·배포 기준

로컬 MVP의 기본 실행 단위는 Docker Compose입니다.

```text
frontend     Vite/React 정적 앱 또는 개발 서버
backend      FastAPI + SQLAlchemy + Alembic
postgres     PostgreSQL
chroma       BGE HTTP mode에서 Compose match profile로 선택 구성
```

- 설정은 환경변수로 주입하고 `.env`는 Git에 올리지 않습니다.
- `.env.example`에는 키 이름과 안전한 예시만 둡니다.
- `/api/v1/demo/reset`은 로컬 시연에서 `DEMO_RESET_ENABLED=true`일 때만 사용하고 공개 배포에서는 기본 비활성 상태를 유지합니다.
- `GET /health/live`는 프로세스 생존 여부, `GET /health/ready`는 DB 연결과 주입된 Provider 이름을 확인합니다.
- 스키마 변경은 Alembic migration으로만 적용합니다.
- Production은 hash 기반 API key와 role을 필수로 사용합니다. SSO/OIDC, tenant,
  key lifecycle, 개인정보 처리와 백업 정책은 별도 설계해야 합니다.

## 10. MVP 비범위

- 실제 ERP/MES 연동
- 실제 기업·수요처 검증
- 물류 주문·계약·결제
- 법적 전자서명 또는 불변 원장
- 실제 인계 완료를 확인하는 외부 증빙
- 검증되지 않은 탄소·전력·폐기물 감축계수
- 멀티테넌시, SSO/OIDC와 세분화된 resource-level 권한 관리
- Evidence의 malware scan·retention·orphan reconcile

## 11. 후속 구현 TODO

- 운영 SSO/OIDC·조직 tenant와 API key rotation/revocation
- Detect import scheduler와 MES/QMS connector
- Evidence malware scan, retention/deletion 및 orphan reconcile worker
- Demand index event의 자동 재시도 worker·backoff·운영 관측
- 다중 API worker용 분산 index lock 또는 단일 전용 index worker
- 실제 인계 증빙이 필요할 경우 별도의 정책·API·법적 검토
