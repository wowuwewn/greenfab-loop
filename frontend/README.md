# GreenFab Loop Frontend

GreenFab Loop의 작동형 해커톤 MVP 프런트엔드입니다. 기존 Insight의 모델 검증 화면과 Loop 의사결정 워크스페이스를 하나의 Next.js 앱으로 구성했습니다.

## 실행

Node.js 22.13 이상을 권장합니다.

```bash
npm install
npm run dev
```

기본 주소는 `http://localhost:3000`입니다.

## 검증

```bash
npm test
```

`npm test`는 ESLint, Data Contract/검색 스냅샷 테스트, Next.js 프로덕션 빌드를 차례로 실행합니다.

## 구현 범위

- REAL SECOM OOF 결과 기반 위험 신호와 SHAP 기여도 표시
- 사람의 자원 발생 확인 게이트
- DEMO Resource Passport
- 합성 입력을 실제 BGE-M3로 실행해 저장한 Top-k 스냅샷
- deterministic 수량·필수정보 Rule Check
- 사람의 `APPROVED / HOLD / REJECTED` 결정
- 승인 수량만 표시하는 최소 ESG Scenario
- Data Contract v0.1 형태의 Green Receipt 초안 JSON 다운로드
- 기존 모델 검증, 운영 개요, ESG 분석 탭

## 데이터 경계

- `app/dashboard_data.json`: 기존 SECOM 모델의 OOF 후향 검증 결과 (`REAL`)
- `app/loop_dataset.json`: 자원·수요·사람 행동을 재현하기 위한 합성 입력 (`DEMO`)
- `app/match_results.json`: 합성 입력을 대상으로 생성한 BGE-M3/TF-IDF 검색 스냅샷 (`DEMO`)
- `app/contract-adapter.js`: 화면 상태를 `docs/data-contract.md`의 top-level envelope와 `snake_case` 필드로 변환하고 런타임 검증

BGE-M3의 `semantic_similarity`는 문장 의미 유사도이며 적합도·성공확률·안전성 확률이 아닙니다. ESG Scenario는 AI 예측이 아니고 실제 감축 실적을 의미하지 않습니다.

## 백엔드 연동 지점

현재 앱은 정적 JSON과 브라우저 상태만으로 동작합니다. API 연동 시 화면 컴포넌트를 직접 변경하기보다 `app/contract-adapter.js` 앞단에 API 응답 정규화 계층을 추가하고, Data Contract v0.1 객체를 단일 경계로 사용합니다.

Green Receipt는 현재 서버 저장·전자서명·불변 감사로그가 없는 다운로드 초안입니다.
