# GreenFab Loop frontend

재원님이 설계한 GreenFab Loop 화면을 FastAPI 워크플로 API에 연결한 React/Vite
클라이언트입니다. 화면의 UCI SECOM 모델 지표는 Golden Case `SECOM-0116` 전용이므로,
서버에 해당 Case가 없을 때 다른 Case를 임의로 대신 표시하지 않습니다.

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

1. `GET /api/v1/cases`에서 Case 목록을 받고 `SECOM-0116`을 확인합니다.
2. `GET /api/v1/cases/SECOM-0116`의 `CaseEnvelope`로 전체 화면 상태를 채웁니다.
3. 현장 확인, Passport, Match, Decision, ESG Scenario, Receipt 요청이 성공할 때마다
   서버가 반환한 최신 `CaseEnvelope`로 로컬 상태를 통째로 교체합니다.
4. Match와 Receipt는 Case/작업별로 안정적인 `Idempotency-Key`를 재시도에 재사용합니다.
5. `409` 응답은 Case를 다시 조회하고, `422` field errors와 `503` trace ID를 UI에
   표시합니다.

모든 API 요청에는 사용자가 입력한 키가 `X-API-Key`로 전송됩니다. Passport/Match/ESG
요청에는 `X-Actor`, Match/Receipt 요청에는 `Idempotency-Key`도 전송됩니다.

## 품질 확인

```bash
npm test
npm run lint
npm run build
```
