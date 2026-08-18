# GreenFab Loop Golden Demo Flow

## 1. 목적

이 문서는 해커톤 심사에서 GreenFab Loop의 핵심 가치를 3분 안에 반복 가능하게 보여주기 위한 Golden Demo 절차입니다. 정상 흐름뿐 아니라 새로고침, 중복 클릭과 모델 장애 시 기대 동작도 정의합니다.

시연에서 반드시 지켜야 할 표현은 다음과 같습니다.

- Detect 결과는 위험 순위이며 불량 확률이 아닙니다.
- SHAP은 모델 예측 기여도이며 공정 원인이나 인과관계가 아닙니다.
- Resource 발생 여부와 Passport는 사람이 확인·입력합니다.
- BGE-M3 점수는 문장 의미 유사도이며 적합도·안전성·성공확률이 아닙니다.
- Rule은 코드로 명시된 조건만 검사하고 최종 결정은 사람이 합니다.
- ESG는 후보 전환량 Scenario이며 실제 감축 실적이 아닙니다.
- Green Receipt는 내부 의사결정 기록이며 법적 인증서나 실제 인계 증명이 아닙니다.

## 2. 시연 전 준비

### Golden fixture

| 항목 | 값·조건 | 출처 |
| --- | --- | --- |
| Case | `SECOM-0116` | 실제 SECOM 기반 결과이면 `REAL` |
| Detect | 위험 순위와 익명 feature SHAP만 표시 | `REAL` |
| 현장 확인 | `demo_operator`가 `CONFIRMED` 입력 | `DEMO` |
| Passport | 설명, 12 kg, 상태, 위치, 구성의 합성 예시 | `DEMO` |
| Demand | 최소 3개의 합성 수요 후보 | `DEMO` |
| Match | Mock 또는 실제 BGE Provider를 화면에 명시 | `DEMO` |
| Decision | `demo_reviewer`의 사람 판단 | 입력 데이터 기준 `DEMO` |
| Scenario | 승인된 후보량 계산 | `SCENARIO` |

`SECOM-0116`에서 Resource 종류나 12 kg이 도출됐다고 설명하면 안 됩니다. Detect와 Resource 데이터는 서로 다른 출처이며, Passport 값은 시연을 위한 DEMO 입력입니다.

### 실행 점검

1. PostgreSQL과 Backend를 실행합니다.
2. Alembic migration이 최신인지 확인합니다.
3. Golden fixture를 seed하고 `POST /api/v1/demo/reset`으로 초기화합니다.
4. `GET /health/live`와 `GET /health/ready`가 모두 성공하는지 확인합니다.
5. 현재 기본 Provider가 Golden R01 전용 고정 DEMO snapshot을 반환하는 `MockMatchProvider`임을 확인합니다.
6. `MATCH_PROVIDER=bge_chroma` 환경이라면 모델과 ChromaDB 인덱스를 미리 로드하고 발표에서 runtime 실행 여부를 분명히 말합니다.
7. 브라우저를 새로고침하고 Overview에서 시작합니다.

## 3. 3분 정상 시연

| 시간 | 화면·행동 | 설명할 핵심 | 기대 상태 |
| --- | --- | --- | --- |
| 0:00–0:25 | Overview에서 위험 Case 선택 | 실제 SECOM 기반 위험 순위로 먼저 볼 건을 좁힌다. 위험 순위는 불량 확률이 아니다. | `CONFIRMATION_PENDING` |
| 0:25–0:45 | Detect 상세에서 SHAP 확인 | 익명 feature가 예측에 미친 영향이며 원인 분석 결과가 아니다. | `CONFIRMATION_PENDING` |
| 0:45–1:00 | 현장 확인을 `CONFIRMED`로 저장 | 모델이 Resource 발생을 추론하지 않고 사람이 실제 발생 여부를 확인한다. | `RESOURCE_CONFIRMED` |
| 1:00–1:20 | DEMO Passport 입력·저장 | SECOM에 없는 자원 설명·수량·상태·위치를 사람이 기록한다. | `PASSPORT_READY` |
| 1:20–1:50 | Match 실행 후 Top-3 확인 | BGE-M3는 의미가 가까운 DEMO 수요를 찾는다. 점수는 의미 유사도다. | `MATCH_READY` |
| 1:50–2:10 | Rule 결과 비교 | `false`는 명시 조건 위반, 누락 필수정보는 추가 확인 대상이다. `null`은 미평가/비적용일 수 있다. | `MATCH_READY` |
| 2:10–2:30 | 사람이 후보 선택·승인 | AI가 아니라 담당자가 후보와 근거를 보고 최종 결정한다. | `DECIDED` |
| 2:30–2:45 | ESG Scenario 생성 | 12 kg은 승인된 Passport 수량 기반 후보 전환량일 뿐 실제 전환 또는 탄소 감축량이 아니다. | `SCENARIO_READY` |
| 2:45–3:00 | Green Receipt 생성·열기 | 결정 당시 입력과 근거를 남긴 내부 JSON 기록이다. 아직 물리적 인계 완료가 아니다. | `RECEIPT_CREATED` |

## 4. 단계별 기대 데이터

### Detect

- `case.source_type`은 실제 SECOM 기반 산출물이면 `REAL`입니다.
- feature는 익명 원본 이름을 유지하며 온도·압력 같은 의미를 임의 부여하지 않습니다.
- 위험도가 확률로 보이도록 `%`를 붙이지 않습니다.

### Resource 확인과 Passport

- 확인 전 Passport 저장 시 `409 INVALID_STATE`가 발생합니다.
- Passport의 DEMO 필드는 `source_type: DEMO`입니다.
- 모르는 값은 임의 생성하지 않고 `null`로 둡니다.
- 수량을 입력하면 단위도 함께 입력합니다.

### Match와 Rule

- 기본 Mock은 `model: Xenova/bge-m3`와 snapshot revision을 함께 저장하고 사전 생성된 고정 DEMO 점수를 표시합니다.
- 이 값은 현재 요청에서 runtime 추론한 결과가 아니라 재현 가능한 고정 snapshot임을 표시합니다.
- Mock은 Passport 설명에 `반도체`, `세정`, `무기질`이 모두 있는 Golden R01 입력만 지원합니다.
- 기본 Mock에서 signature가 없는 자유 입력은 `503 MATCH_UNAVAILABLE`입니다. 자유 입력은 optional dependency를 설치하고 `MATCH_PROVIDER=bge_chroma`를 명시한 환경에서 실행합니다.
- `MATCH_PROVIDER=bge_chroma`일 때만 현재 요청에서 계산한 `semantic_similarity`라고 설명합니다.
- 후보는 Top-3이며 각 후보에 Rule 결과와 `REVIEW`, `NEEDS_INFO`, `RULE_FAIL` 중 하나를 표시합니다.
- Rule 우선순위는 수량·위치 검사에 명시적인 `false`가 있으면 `RULE_FAIL`, `required_info: false` 또는 필수정보가 부족하면 `NEEDS_INFO`, 그 외는 `REVIEW`입니다.
- 위치 조건이 설정되지 않아 `location: null`인 후보는 `미평가`로 표시할 수 있으며, `null`만으로 `NEEDS_INFO`가 되지는 않습니다.

### Decision

- `APPROVED`, `HOLD`, `REJECTED`는 사람만 입력합니다.
- 승인 시 실제 Match 후보의 `demand_id`와 결정 사유가 필요합니다.
- Decision 화면에는 결정자와 시각을 표시합니다.

### ESG Scenario

정상 승인 흐름의 최소 수식은 다음과 같습니다.

```text
APPROVED && passport.quantity is known
candidate_diversion_quantity = passport.quantity

APPROVED && passport.quantity is unknown
candidate_diversion_quantity = null

HOLD or REJECTED
candidate_diversion_quantity = 0
```

- `source_type`은 반드시 `SCENARIO`입니다.
- `formula_version`은 `candidate_diversion_v0.1`입니다.
- 환산계수를 사용하지 않으므로 `factor_source`는 `null`입니다.
- CO2e, 탄소 감축률, 비용 절감액을 임의 계산하지 않습니다.

### Green Receipt

- `decision_status`와 생성 당시 전체 Case 스냅샷이 일치해야 합니다.
- 승인된 정상 흐름의 `handoff_status`는 `APPROVED`입니다.
- `HANDOFF_CONFIRMED`는 실제 외부 인계 증빙을 수집하는 기능이 없는 MVP에서 사용하지 않습니다.
- 화면과 다운로드 파일에 법적 인증서가 아니라는 안내를 표시합니다.

## 5. 필수 예외 시연·테스트

### A. Resource 미발생

```text
CONFIRMATION_PENDING
→ NOT_CONFIRMED
→ CLOSED
```

- Passport 이후 버튼이 비활성화됩니다.
- API에서 Passport 저장을 시도하면 `409 INVALID_STATE`입니다.
- Match, Decision, Scenario, Receipt는 모두 `null`입니다.

### B. Passport 필수 입력 누락

- 비어 있는 설명 등 Match에 필요한 필드를 저장하려 하면 `422 VALIDATION_ERROR`입니다.
- 누락값을 임의 생성하거나 기본 물질명으로 대체하지 않습니다.

### C. Match Provider 장애

- `MATCH_PROVIDER=bge_chroma` 환경의 장애는 `503 MATCH_UNAVAILABLE`입니다.
- 기본 Mock에 Golden R01 signature가 없는 자유 입력을 보내도 `503 MATCH_UNAVAILABLE`입니다. 고정 R01 점수를 무관한 Passport에 재사용하지 않습니다.
- Backend가 조용히 Mock 결과로 전환하지 않습니다.
- 기본 Mock 환경과 실제 BGE 환경을 시연 전에 명확히 선택하고 표시합니다.

### D. Rule 결과

- 수량 또는 위치의 명시 조건이 `false`이면 `RULE_FAIL`입니다.
- `missing_fields`가 존재하거나 `required_info: false`이면 `NEEDS_INFO`입니다.
- 조건이 설정되지 않아 `null`인 항목은 `미평가/비적용`이며 그것만으로 실패하지 않습니다.

### E. 중복 클릭과 새로고침

- Match와 Receipt에 `Idempotency-Key`를 보내는 것을 권장하며, 같은 Case에서 같은 키를 다시 사용하면 기존 결과를 반환합니다.
- key 범위는 Case이므로 다른 Case에서는 같은 문자열 key를 사용할 수 있습니다.
- 같은 Case의 동시 재시도는 Case row lock과 DB Unique 제약으로 Match/Receipt 한 건만 유지합니다.
- Scenario는 Case당 하나이며 재호출해도 같은 결과를 반환합니다.
- 브라우저를 새로고침해도 PostgreSQL의 현재 단계와 입력값이 복원됩니다.
- Receipt는 중복 생성되지 않습니다.

## 6. Demo reset

`POST /api/v1/demo/reset`은 로컬 시연 환경에서 `DEMO_MODE=true`와 `DEMO_RESET_ENABLED=true`를 함께 설정한 경우에만 활성화합니다. reset flag 기본값은 `false`입니다.

- Golden Case `SECOM-0116`과 연결된 Workflow 데이터만 초기 상태로 되돌립니다.
- 다른 Case와 공용 Demand는 보존합니다.
- 실제 `REAL` 원본 산출물 자체를 삭제하거나 다시 학습하지 않습니다.
- DEMO Match, Decision, Scenario, Receipt, Audit 데이터를 재생성 가능한 상태로 정리합니다.
- 공개 배포에서는 비활성 기본을 유지해야 합니다.

## 7. 시연 완료 기준

- 같은 Golden Demo를 3회 연속 실행할 수 있습니다.
- 정상 흐름이 3분 내 `RECEIPT_CREATED`에 도달합니다.
- 새로고침 후 진행 상태가 유지됩니다.
- 각 화면에서 `REAL`, `DEMO`, `SCENARIO`가 명확히 구분됩니다.
- 고정 DEMO snapshot과 실제 BGE runtime 실행 여부를 혼동시키지 않습니다.
- Receipt JSON을 열어 Case, Passport, Match, Decision, Scenario를 추적할 수 있습니다.
- 실제 인계·탄소 감축·법적 인증으로 과장하는 문구가 없습니다.
