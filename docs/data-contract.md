# GreenFab Loop MVP Data Contract v0.1

## 1. 문서 목적

이 문서는 GreenFab Loop 해커톤 MVP에서 Frontend / Backend / AI가 주고받는 JSON 필드명과 최소 형식을 맞추기 위한 Data Contract v0.1입니다. 구현 언어나 저장 방식이 달라도 이 문서의 `snake_case` 필드명을 공통으로 사용합니다.

전체 흐름은 다음과 같습니다.

`Detect` → 사람의 실제 Resource 발생 확인 → `Resource Passport` → `BGE-M3 Semantic Match` → deterministic `Rule Check` → `Human Decision` → `ESG Scenario` → `Green Receipt`

## 2. 데이터 출처 구분

`source_type`은 코드를 실제로 실행했는지가 아니라 데이터의 출처(provenance)를 구분합니다.

| `source_type` | 의미 | MVP 예시 |
| --- | --- | --- |
| `REAL` | 실제 SECOM 데이터 또는 이를 입력으로 계산한 결과 | 실제 SECOM 데이터, Detect 결과, risk rank, SHAP 결과 |
| `DEMO` | 해커톤용 합성 데이터 또는 이를 입력으로 계산한 결과 | 합성 Resource Passport, 합성 수요 기업·설명, 데모용 사용자 확인 정보, BGE-M3 Match 결과 |
| `SCENARIO` | 사용자 입력값과 명시된 계산식으로 만든 결과 | ESG Scenario 계산 결과 |

SECOM은 불량 위험 분석에만 사용합니다. SECOM에 Resource, 폐기물 또는 재활용 정보가 있다고 가정하지 않습니다. SHAP은 모델 예측에 영향을 준 변수이며 실제 원인이나 인과관계가 아닙니다.

BGE-M3의 `semantic_similarity`는 DEMO 텍스트를 입력으로 사용하더라도 모델을 실제로 실행해 계산한 값이어야 합니다. BGE-M3를 실제 실행했더라도 입력 Resource와 Demand가 `DEMO`이면 Match 결과의 `source_type`도 `DEMO`입니다. 이 값은 문장 의미 유사도일 뿐, 실제 산업 적합성 데이터, `REAL` 산업 데이터, 재활용 성공 확률 또는 안전성 확률로 표현하지 않습니다.

ESG는 AI 예측이 아니라 사용자 입력값 기반의 `SCENARIO` 계산입니다. AI는 `APPROVED`, `HOLD`, `REJECTED`의 최종 결정을 내리지 않으며 최종 결정은 사람이 입력합니다.

## 3. 공통 JSON 구조

API와 mock JSON은 다음 top-level key를 사용합니다. 아직 도달하지 않은 단계의 객체는 `null`로 둘 수 있습니다.

```text
case
resource_confirmation
resource_passport
match
decision
esg_scenario
receipt
```

시간 필드는 ISO 8601 문자열을 사용합니다. 예: `2026-08-17T10:00:00+09:00`.

## 4. 각 객체의 최소 필드

### `case`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `case_id` | string | 생산 건 식별자 |
| `risk_rank` | integer \| null | Detect 결과의 위험 순위 |
| `shap_top_features` | array \| null | SHAP 영향도가 큰 변수 목록 |
| `source_type` | string | 실제 SECOM 기반 Detect는 `REAL`, mock 데이터는 `DEMO` |

`shap_top_features`의 각 원소는 `feature_name`과 `shap_value` 두 필드만 가집니다. SHAP 값은 해당 모델 예측에 영향을 준 변수와 영향 값이며, 실제 공정 원인이나 인과관계를 의미하지 않습니다. SECOM 변수는 익명화되어 있으므로 온도, 압력 같은 실제 공정 요소 이름을 임의로 붙이지 않습니다.

### `resource_confirmation`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `status` | string | `PENDING`, `CONFIRMED`, `NOT_CONFIRMED` 중 하나 |
| `confirmed_by` | string \| null | 실제 발생 여부를 확인한 사람 |
| `confirmed_at` | string \| null | 확인 시각 |
| `source_type` | string | 확인 정보의 출처: `REAL` 또는 `DEMO` |

사람이 실제 Resource 발생을 `CONFIRMED`한 뒤에만 `Resource Passport` 단계로 넘어갑니다. `NOT_CONFIRMED`이면 이후 매칭 흐름을 진행하지 않습니다.

### `resource_passport`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `passport_id` | string | Resource Passport 식별자 |
| `description` | string \| null | Resource 설명 |
| `quantity` | number \| null | 수량 |
| `unit` | string \| null | 수량 단위 |
| `condition` | string \| null | 상태 설명 |
| `location` | string \| null | 보관 또는 발생 위치 |
| `composition` | string \| null | 재질·구성 정보 |
| `source_type` | string | MVP 합성 정보는 `DEMO` |

모르는 Resource 정보는 임의로 만들지 않고 `null`을 사용합니다.

### `match`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `model` | string | 사용한 임베딩 모델명 |
| `created_at` | string \| null | 매칭 실행 시각 |
| `source_type` | string | MVP의 합성 Resource / Demand를 사용한 Match는 `DEMO` |
| `candidates` | array | Top-k 수요 후보 목록 |

각 candidate의 최소 필드는 다음과 같습니다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `demand_id` | string | 수요 건 식별자 |
| `company_name` | string | 수요 기업명 |
| `demand_description` | string | 수요 설명 |
| `semantic_similarity` | number \| null | BGE-M3가 실제 계산한 문장 의미 유사도 |
| `rule_check` | object | deterministic Rule Check 결과 |
| `status` | string | `REVIEW`, `NEEDS_INFO`, `RULE_FAIL` 중 하나 |

candidate의 `status` 의미는 다음과 같습니다.

- `REVIEW`: 사람이 검토할 후보
- `NEEDS_INFO`: 필수정보가 부족해 추가 확인이 필요한 후보
- `RULE_FAIL`: 코드로 명확히 정의된 deterministic Rule을 충족하지 못한 후보

`semantic_similarity`는 숫자로 저장하지만 이를 “적합도” 또는 “성공 확률”이라고 부르지 않습니다. 후보의 `status`는 검토 상태이며 사람의 최종 `decision.status`와 다릅니다. 특히 `RULE_FAIL`은 사람의 최종 `REJECTED` 결정이 아닙니다.

### `rule_check`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `quantity` | boolean \| null | 명시된 수량 조건 충족 여부 |
| `required_info` | boolean \| null | 필수정보 존재 여부 |
| `location` | boolean \| null | 명시된 위치 조건 충족 여부 |
| `missing_fields` | array \| null | 누락된 필드명 목록 |

Rule Checker는 수량, 필수정보, 위치처럼 코드로 명확히 표현한 조건만 검사합니다. LLM이 조건을 만들거나 임의로 통과 여부를 판단하지 않습니다.

### `decision`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `status` | string | `APPROVED`, `HOLD`, `REJECTED` 중 하나 |
| `selected_demand_id` | string \| null | 사람이 선택한 수요 건 식별자 |
| `reason` | string \| null | 결정 사유 |
| `decided_by` | string | 최종 결정자 |
| `decided_at` | string | 최종 결정 시각 |

최종 `decision`은 AI가 아니라 사람이 입력합니다.

### `esg_scenario`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `source_type` | string | 반드시 `SCENARIO` |
| `inputs` | object | 사용자가 입력한 계산값 |
| `results` | object | 명시된 계산식의 결과 |
| `formula_version` | string \| null | 계산식 버전 |
| `factor_source` | string \| null | 사용한 환산계수의 출처 |

`inputs`와 `results` 내부 필드는 ESG 계산식을 확정할 때 추가합니다. 확정되지 않은 값은 만들지 않고 `null` 또는 빈 객체를 사용합니다.

### `receipt`

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `receipt_id` | string | Green Receipt 식별자 |
| `case_id` | string | 연결된 생산 건 식별자 |
| `passport_id` | string | 연결된 Resource Passport 식별자 |
| `selected_demand_id` | string \| null | 선택된 수요 건 식별자 |
| `decision_status` | string | 사람의 최종 결정 상태 |
| `handoff_status` | string | 예: `RESOURCE_CONFIRMED`, `APPROVED`, `HANDOFF_CONFIRMED` |
| `created_at` | string \| null | 기록 생성 시각 |

Green Receipt는 법적 인증서가 아니라 GreenFab Loop MVP 내부의 의사결정 및 이력 기록입니다.

## 5. JSON 예시

아래는 필드 연결을 확인하기 위한 mock JSON입니다. 운영 환경에서는 사람이 실제 Resource 발생 여부를 확인하지만, 이 예시는 그 확인 과정을 `DEMO` 데이터로 재현합니다. 실제 BGE-M3 실행 전이므로 `semantic_similarity`는 `null`입니다.

```json
{
  "case": {
    "case_id": "CASE-001",
    "risk_rank": null,
    "shap_top_features": [],
    "source_type": "DEMO"
  },
  "resource_confirmation": {
    "status": "CONFIRMED",
    "confirmed_by": "demo_operator",
    "confirmed_at": "2026-08-17T10:00:00+09:00",
    "source_type": "DEMO"
  },
  "resource_passport": {
    "passport_id": "PASSPORT-DEMO-001",
    "description": "DEMO Resource 설명",
    "quantity": null,
    "unit": null,
    "condition": null,
    "location": null,
    "composition": null,
    "source_type": "DEMO"
  },
  "match": {
    "model": "BAAI/bge-m3",
    "created_at": null,
    "source_type": "DEMO",
    "candidates": [
      {
        "demand_id": "DEMAND-DEMO-001",
        "company_name": "DEMO 수요 기업",
        "demand_description": "DEMO 수요 설명",
        "semantic_similarity": null,
        "rule_check": {
          "quantity": null,
          "required_info": null,
          "location": null,
          "missing_fields": null
        },
        "status": "REVIEW"
      }
    ]
  },
  "decision": {
    "status": "HOLD",
    "selected_demand_id": null,
    "reason": "추가 검토 대기",
    "decided_by": "demo_reviewer",
    "decided_at": "2026-08-17T10:30:00+09:00"
  },
  "esg_scenario": null,
  "receipt": null
}
```

## 6. 팀 통합 규칙

- 새로운 필드가 필요하면 혼자 이름을 바꾸지 말고 이 Data Contract를 먼저 수정합니다.
- Frontend / Backend / AI 모두 같은 `snake_case` 필드명을 사용합니다.
- unknown 값은 임의 생성하지 않고 `null`을 허용합니다.
- `REAL` / `DEMO` / `SCENARIO`를 혼동하지 않습니다.
- `semantic_similarity`를 `compatibility_score` 같은 이름으로 바꾸지 않습니다.
- API 연결 전 mock JSON도 이 계약을 따릅니다.

## TODO

- ESG `inputs`와 `results`의 세부 필드 및 계산식 확정
- Rule Checker의 수량·위치 조건과 판정 기준 확정
- API 구현 전 요청·응답별 필수값과 오류 형식 확정
