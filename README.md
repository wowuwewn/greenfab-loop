# GreenFab Loop

> 버려진 다음 찾는 게 아니라, 버려지기 전에 다음 경로를 준비합니다.

GreenFab Loop는 제조 데이터에서 불량 위험이 높은 생산 건을 먼저 선별하고, 실제 자원 발생이 확인된 경우 `Resource Passport`를 작성해 다음 활용 경로를 준비하는 제조 자원 순환 의사결정 지원 서비스입니다. `BGE-M3` 기반 `Semantic Match`로 의미가 가까운 수요 후보를 찾고, `Rule Checker`와 사람의 최종 판단을 거쳐 `ESG Scenario`와 `Green Receipt`를 남깁니다.

## 핵심 흐름

`Detect` → `Resource Passport` → `Semantic Match` → `Rule / Human Decision` → `ESG Scenario` → `Green Receipt`

## 폴더 구성

- `frontend/`: 사용자 화면과 상호작용을 담당합니다.
- `backend/`: API, 업무 흐름, 데이터 연계를 담당합니다.
- `ai/`: 위험 탐지(`detect`), 의미 기반 후보 검색(`match`), 규칙 검사(`rules`), 근거 검색·정리(`rag`)를 담당합니다.
- `data/`: 실제 데이터, 데모 데이터, 생성 결과물을 구분해 관리합니다.
- `docs/`: 팀 공통 계약, 시스템 구조, 데모 흐름을 문서화합니다.

## 데이터 구분

- `REAL`: 실제 출처와 실제 관측값에 기반한 데이터입니다.
- `DEMO`: 해커톤 시연을 위해 준비한 예시 또는 합성 데이터입니다.
- `SCENARIO`: 사용자 입력값과 명시된 가정으로 계산한 시나리오 결과이며, AI 예측값이 아닙니다.

## 중요한 해석 주의사항

- SECOM은 불량 위험 분석에만 사용하며, 자원·폐기물·재활용 정보가 있다고 가정하지 않습니다.
- SHAP은 실제 원인이나 인과관계가 아니라 모델 예측에 영향을 준 변수를 설명합니다.
- Semantic similarity는 재활용 적합도, 성공 확률 또는 안전성 확률을 뜻하지 않습니다.
- ESG 수치는 AI 예측이 아니라 사용자 입력값 기반의 Scenario 계산 결과입니다.
- AI는 최종 승인이나 거절을 결정하지 않으며, 최종 판단은 사람이 수행합니다.

## 현재 상태

현재는 팀 협업을 위한 초기 프로젝트 구조를 구성한 단계입니다. 애플리케이션, AI 모델, 데이터베이스 등의 실제 기능은 아직 구현하지 않았습니다.

## 팀 작업 가이드

| 폴더 | 역할 | 주요 작업 |
| --- | --- | --- |
| `frontend/` | Frontend | Figma 기준 GreenFab Loop 웹 구현 |
| `backend/` | Backend | Resource Passport, Decision, Green Receipt 저장 및 API |
| `ai/detect/` | AI/Data | SECOM, LightGBM, SHAP 기반 위험 생산 건 선별 |
| `ai/match/` | AI | BGE-M3 기반 Semantic Match Top-k 후보 검색 |
| `ai/rules/` | Rule | 수량, 필수정보 등 deterministic 조건 확인 |
| `ai/rag/` | RAG | 공식 문서와 근거 검색 보조 |
| `data/real/` | 공용 데이터 | 실제 SECOM 및 실제 모델 결과 |
| `data/demo/` | 공용 데이터 | Resource Passport, 수요처 등 DEMO 데이터 |
| `data/outputs/` | 공용 데이터 | Match, Rule 등의 실행 결과 |
| `docs/` | 공용 문서 | 데이터 계약, 시스템 구조, 데모 흐름 |

### 핵심 개발 흐름

```text
Detect
→ Resource Passport
→ Semantic Match
→ Rule Check
→ Human Decision
→ ESG Scenario
→ Green Receipt
```

### 협업 원칙

- 각 담당자는 가능한 자기 담당 폴더를 중심으로 수정한다.
- 공통 데이터 필드명은 `docs/data-contract.md`를 기준으로 맞춘다.
- REAL / DEMO / SCENARIO를 구분한다.
- `main` 브랜치는 최종 안정본으로 사용하고, 기능 개발은 별도 브랜치에서 진행할 예정이다.
- API key, secret, `.env` 파일은 GitHub에 올리지 않는다.

## Figma 디자인

GreenFab Loop의 전체 화면, 디자인 시스템, 반응형 기준과 3분 데모 프로토타입은
[Figma 디자인 핸드오프](docs/design/greenfab-loop-figma.md)에서 확인할 수 있습니다.
