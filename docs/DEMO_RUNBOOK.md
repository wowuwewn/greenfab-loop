# GreenFab Loop Golden Demo Runbook

## 0. 발표 메시지

**BEFORE** 생산 위험 신호에서 먼저 확인 → **FIND** 표현이 다른 DEMO 수요 후보를 BGE-M3 의미 검색으로 탐색 → **PROVE** Rule + Human Decision + ESG Scenario를 Green Receipt로 기록.

실무 가치 한 문장: GreenFab Loop는 모든 생산 건을 동일하게 확인하는 대신 위험 상위 건을 먼저 확인하고, 실제 자원이 발생했을 때 관련 수요 후보와 검토 근거를 한 흐름에서 제공해 담당자가 더 빠르게 다음 조치를 검토하도록 돕는 의사결정 지원 서비스입니다.

## 1. 실제 BGE Backend 사전 기동

발표 환경은 **로컬 WSL + CPU BGE-M3**를 기준으로 한다. Backend `.env`에서 PostgreSQL 연결과 아래 값을 확인한다. 공개 배포에서는 Demo reset을 켜지 않는다.

```text
MATCH_PROVIDER=bge_chroma
BGE_MODEL_NAME=BAAI/bge-m3
BGE_MODEL_REVISION=5617a9f61b028005a4858fdac845db406aefb181
BGE_DEVICE=cpu
CHROMA_MODE=persistent
CHROMA_PERSIST_DIRECTORY=.data/chroma
DEMO_MODE=true
SEED_DEMO_DATA=true
DEMO_RESET_ENABLED=true
```

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

모델 첫 로드와 Demand index 동기화가 끝날 때까지 기다린다. 다른 터미널에서 다음 응답을 확인하기 전에는 발표를 시작하지 않는다.

```bash
curl --fail http://127.0.0.1:8000/health/ready
```

필수 증거: `status=ready`, `match_provider=BgeChromaMatchProvider`. 모델·revision과 실제 encode/Chroma query까지 재검증할 때에는 **공유 DB가 아닌 isolated DB/Chroma 경로**로 `python scripts/verify_bge_golden.py`를 실행한다.

## 2. Frontend 기동

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

`http://127.0.0.1:5173`을 열고 브라우저 개발자 도구의 Network 오류가 없는지 확인한다.

## 3. Golden Demo 입력과 순서

`Demo reset → Detect SECOM-0116 → Confirm → Passport → Match → Review → ESG → Receipt → Verify`

Passport 입력:

```text
자원 설명: 반도체 세정 공정에서 회수된 DEMO 미세 무기질 분말
수량: 12
단위: kg
상태: 건조 분말
위치: 제조동 A
구성: 이산화규소 중심 합성 DEMO 성분표
```

Decision 예시: D01 선택, `파일럿 검토 승인`, 사유 `성분 분석 완료 후 소량 파일럿 검토를 진행합니다.`

ESG는 기본 수량 12kg, `기존 폐기 처리 → 세라믹 원료 파일럿 활용`을 확인한다. 검증된 실제 계수가 없으면 에너지·탄소 계수는 비워 둔다.

예상 실제 BGE Top-3:

| 순위 | 후보 | semantic similarity |
| ---: | --- | ---: |
| 1 | D01 | 약 0.5420 |
| 2 | D15 | 약 0.5356 |
| 3 | D11 | 약 0.5134 |

Mock snapshot `0.649156 / 0.629172 / 0.602390`과 혼동하지 않는다. similarity는 문장 의미의 가까움이며 산업 적합도·안전성·성공 확률이 아니다.

## 4. Reset과 새로고침 확인

- 화면의 `데모 처음부터 다시` 또는 `POST /api/v1/demo/reset`은 Golden Case만 초기화한다.
- Passport, Match, Decision, ESG, Receipt 단계에서 각각 새로고침하면 URL hash의 단계와 Backend CaseEnvelope가 복원되어야 한다.
- Receipt의 `Receipt 다시 확인하기`는 `#/verify/{receipt_id}`에서 저장 snapshot을 read-only로 조회한다.
- `최종 검토로 돌아가기` 후 Match, 선택 candidate, Decision이 유지되어야 한다.
- `PDF 저장 / 인쇄`는 브라우저 print dialog를 열어야 한다.

## 5. 명시적 Mock 실행

실제 BGE 서버를 중지하고 `.env`의 `MATCH_PROVIDER=mock`으로 **명시 변경한 뒤** Backend를 재시작한다. Mock은 Golden Passport signature 전용 precomputed snapshot이며 임의 Passport에는 같은 Top-3를 반환하지 않는다.

```text
MATCH_PROVIDER=mock
DEMO_RESET_ENABLED=true
```

`/health/ready`가 `MockMatchProvider`인지 확인하고 reset → confirmation → passport → match → decision을 실행한다. 실제 BGE 실패 시 서버가 조용히 Mock으로 전환하지 않는다.

## 6. 장애 시 발표자 행동

1. `/health/ready`가 503이거나 provider가 다르면 실제 BGE라고 발표하지 않는다. Backend log와 model/Chroma 설정을 확인하고 한 번만 재기동한다.
2. 복구가 늦으면 **“실제 BGE runtime 장애로 명시적 Golden snapshot 모드로 전환한다”**고 알린 뒤 Mock 서버를 별도로 기동한다. 두 점수 세트를 섞지 않는다.
3. API 409는 현재 단계 불일치이므로 Demo reset 후 재시작한다. 422는 Passport/Decision/ESG 입력 메시지를 수정한다. 503·네트워크 오류는 화면의 재시도 경로를 사용하되 무한 대기하지 않는다.

## 7. 검증 범위와 한계

검증: SECOM 위험 우선순위, 실제 BGE-M3 embedding·Chroma 검색, Top-3, deterministic Rule/Human 분리, Golden E2E, Backend Receipt 저장·조회.

미검증: 실제 수요처 적합성, 실제 재활용 가능성·안전성, 실제 ESG 감축 효과, 제조업 전체 일반화. 그래서 AI는 후보만 찾고 Rule이 명확한 조건을 확인하며 사람이 최종 판단한다. Green Receipt는 내부 의사결정 기록이지 법적 인증서가 아니다.
