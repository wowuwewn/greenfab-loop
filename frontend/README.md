# GreenFab Loop frontend

재원님이 설계한 GreenFab Loop 화면을 FastAPI 워크플로 API에 연결한 React/Vite
클라이언트입니다. API에서 받은 위험 Case를 운영 큐로 보여주며, 사용자는 Case별
현재 상태와 다음 작업을 확인하고 독립적으로 워크플로를 진행할 수 있습니다.
`SECOM-0116`은 진행 가능한 경우 시연 추천 Case로 표시할 뿐 유일한 실행 대상은
아닙니다. 종료된 Case는 결과만 조회할 수 있습니다.

## 로컬 실행

```bash
npm install
npm run dev
```

기본 개발 서버는 `/api` 요청을 `http://127.0.0.1:8000`으로 프록시합니다. 별도
백엔드 origin을 사용할 때만 `.env.local`에 아래 값을 설정합니다.

```dotenv
VITE_API_BASE_URL=https://your-api.example.com
```

`VITE_API_BASE_URL`에는 `/api/v1`을 붙이지 않습니다. API 키는 `VITE_*` 환경 변수에
넣지 마세요. Vite 빌드 산출물에 공개될 수 있습니다. 운영 API 키는 접속 화면에서
입력하며 현재 탭의 메모리와 `sessionStorage`에만 유지됩니다.

## API 흐름

1. `GET /api/v1/cases?limit=100&offset=0`에서 검토 Case 목록과 현재 상태를 받습니다.
2. 진행 가능한 `SECOM-0116`을 우선 안내하고, 이미 종료됐다면 상태·순위 규칙에 따라
   다음 진행 가능한 Case를 안내합니다. 사용자는 운영 큐에서 다른 Case도 선택할 수 있습니다.
3. `GET /api/v1/cases/{case_id}`의 `CaseEnvelope`로 선택 Case의 상세 화면을 채웁니다.
4. 현장 확인, Passport, Match, Decision, ESG Scenario, Receipt 요청이 성공할 때마다
   서버가 반환한 최신 `CaseEnvelope`로 로컬 상태를 통째로 교체합니다.
5. 목록 응답에는 단계 상태가 있으므로 변경 성공 및 `409` 충돌 뒤 목록을 다시 조회해
   운영 큐와 상세 화면을 동기화합니다.
6. Match와 Receipt는 Case/작업별로 안정적인 `Idempotency-Key`를 재시도에 재사용합니다.
7. `409` 응답은 Case를 다시 조회하고, `422` field errors와 `503` trace ID를 UI에
   표시합니다.

모든 API 요청에는 사용자가 입력한 키가 `X-API-Key`로 전송됩니다. Passport/Match/ESG
요청에는 `X-Actor`, Match/Receipt 요청에는 `Idempotency-Key`도 전송됩니다.

## 품질 확인

```bash
npm test
npm run lint
npm run build
```
