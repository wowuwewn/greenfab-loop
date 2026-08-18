# GreenFab Loop Figma Design Handoff

GreenFab Loop의 운영형 B2B SaaS UI, 디자인 시스템, 반응형 기준, 데모 프로토타입을 정리한 핸드오프 문서입니다.

## 바로가기

- [Figma 파일 열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd)
- [3분 데모 프로토타입 시작 화면](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=55-2)
- [컴포넌트 라이브러리](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=17-2)
- [데스크톱 전체 화면](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=5-4)
- [반응형 화면](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=5-5)

관련 구현 PR:

- [Frontend MVP PR #2](https://github.com/wowuwewn/greenfab-loop/pull/2)
- [SECOM Detect pipeline PR #3](https://github.com/wowuwewn/greenfab-loop/pull/3)

## 제품 방향

> GreenFab Insight가 생산 위험을 발견하고, GreenFab Loop가 실제 자원 확인부터 활용처 후보 검토, 사람의 최종 결정, 근거 기록까지 연결합니다.

핵심 흐름은 다음 8단계입니다.

`Detect → Confirm → Passport → Match → Rule → Human Decision → ESG Scenario → Green Receipt`

AI는 후보와 근거를 제공하지만 최종 결정은 담당자가 기록합니다. 화면은 제조 현장의 운영 SaaS로 보이도록 업무 상태, 차단 조건, 다음 행동을 우선 표시합니다.

## Figma 파일 구조

| 페이지 | 내용 |
| --- | --- |
| `00 Cover & Demo Map` | 제품 문장과 전체 데모 흐름 |
| `01 Foundations` | 색상, 타이포그래피, 간격, radius, elevation, 언어 원칙 |
| `02 Components` | 버튼, 배지, Stepper, Human Gate, Passport, Match, Rule, Decision, Receipt 등 |
| `03 Desktop Screens` | 1440×1024 기준 핵심 제품 화면 8개 |
| `04 Responsive` | Tablet 1024, Mobile 390 레이아웃 |
| `05 Prototype & States` | 번호 액션으로 연결된 7개 시연 상태 |

## 데스크톱 화면

| 화면 | Figma | 목적 |
| --- | --- | --- |
| Operations Overview | [열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=35-2) | 검토 대기, 현장 확인, 매칭, 전환 후보량과 다음 업무 요약 |
| Detect & Confirm | [열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=37-99) | SECOM OOF 위험 신호와 사람의 현장 확인 분리 |
| Resource Passport | [열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=40-188) | 자원 정보와 성분 분석 차단 조건 관리 |
| AI Match & Rule Check | [열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=42-311) | BGE-M3 의미 유사도와 결정론적 규칙을 별도로 검토 |
| Human Decision | [열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=43-535) | 담당자의 상태, 사유, AI 한계 확인 기록 |
| ESG Scenario | [열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=44-629) | 승인 상태와 확인 수량 기반 전환 후보량 계산 |
| Green Receipt | [열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=46-643) | 입력·모델·규칙·사람 결정·시나리오의 로컬 JSON 초안 |
| Model Trust | [열기](https://www.figma.com/design/PgbnCCqAQZlBNpHGOcWAJd?node-id=48-735) | 모델 선정 규칙, OOF 성능, 혼동행렬과 검증 한계 공개 |

## 디자인 시스템 현황

- Variables 97개
- Text styles 9개
- Effect styles 2개
- Component sets 16개
- Component variants 121개
- 공통 App Shell과 반복 업무 컴포넌트 사용
- 기본 글꼴: `Noto Sans KR` — 코드에서는 `Pretendard Variable` 우선, `Noto Sans KR` fallback 권장
- 본문 최소 14px, 터치 대상 최소 44px
- 배경·텍스트·상태·근거 색상을 semantic variable로 분리

## 3분 데모 실행

1. Figma의 `05 Prototype & States` 페이지로 이동합니다.
2. `Prototype/01 Overview` 프레임을 선택합니다.
3. 우측 상단 `Present`를 실행합니다.
4. 화면 상단의 초록색 번호 액션을 순서대로 클릭합니다.

프로토타입 연결:

`Overview → Detect & Confirm → Passport Blocked → Match & Rule → Human Decision → ESG Scenario → Receipt Success`

첫 프레임은 Figma flow starting point로 설정되어 있고, 6개의 화면 전환이 연결되어 있습니다.

## 데이터와 표현 원칙

### 근거 구분

- `REAL`: UCI SECOM 후향 데이터 기반 Detect 입력
- `DEMO`: 합성 자원·수요 데이터와 이를 사용한 데모 매칭·규칙 결과
- `SCENARIO`: 사용자의 입력과 결정 상태를 이용한 시나리오 계산
- `LOCAL DRAFT`: 저장 상태 또는 산출물 상태이며 Data Contract의 `source_type`이 아님

Data Contract v0.1의 `source_type`은 `REAL / DEMO / SCENARIO`만 사용합니다. `COMPUTED`, `HUMAN`, `LOCAL`을 source enum으로 추가하지 않습니다.

### 금지하거나 주의할 표현

- 상대 위험 백분위를 `불량 확률`로 표현하지 않습니다.
- SHAP을 공정 원인 또는 인과효과로 표현하지 않습니다.
- BGE-M3 `semantic_similarity`를 적합도, 안전성, 성공확률로 표현하지 않습니다.
- `REVIEW`를 승인으로 표현하지 않습니다.
- `APPROVED`는 담당자의 결정이며 실제 인계 완료가 아닙니다.
- ESG Scenario의 12kg은 전환 후보량이며 실제 감축 또는 인계 실적이 아닙니다.
- Green Receipt는 법적 인계서, 적합성 인증서, 전자서명 문서, 불변 감사로그가 아닙니다.

## 프런트 구현 기준

1. `01 Foundations`의 semantic token을 CSS variable 또는 Tailwind theme에 매핑합니다.
2. `02 Components`의 variants를 React component props와 상태 enum으로 옮깁니다.
3. `03 Desktop Screens`를 1440px 기준선으로 구현합니다.
4. `04 Responsive`의 Tablet 1024와 Mobile 390 시안을 breakpoint 기준으로 사용합니다.
5. Data Contract adapter를 UI 내부 상태보다 우선합니다.
6. `null`은 0이나 실패가 아니라 `미확인`, `미평가`, `규칙 미정`으로 구분합니다.
7. 현장 확인 전에는 Passport 이후 상태를 잠그고, `NOT_CONFIRMED`이면 후속 객체를 `null`로 종료합니다.

## 검수 결과

- 데스크톱 화면 8개: 1440×1024, 겹침 없음
- 반응형 화면 2개: Tablet 1024, Mobile 390
- 12px 미만 텍스트 0개
- 화면 밖 텍스트 0개
- Prototype state 7개, action control 7개, transition 6개
- Alert, NextAction, HumanGate의 텍스트 자동 높이 보정 완료
- 긴 버튼 라벨과 Receipt provenance 열 잘림 수정 완료

## 현재 범위 밖

- Figma Code Connect 매핑
- 백엔드 API 및 인증 연결
- 서버 영속 저장, 전자서명, 불변 감사로그
- 실제 폐기물 인계 또는 감축 실적 검증
- 운영 데이터 기반 매칭 성능 검증

이 문서는 프런트 구현과 발표 시연을 위한 기준선입니다. 화면 문구나 데이터 상태를 변경할 때는 `docs/data-contract.md`와 함께 갱신합니다.
