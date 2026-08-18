# Render Backend 배포 가이드

이 문서는 `render.yaml`로 FastAPI, Render Postgres, 실제 BGE-M3와 embedded
Chroma를 배포하기 전 확인할 운영 계약입니다. Blueprint 파일을 커밋하거나
push하는 것만으로 리소스가 생성되지는 않습니다. Render Dashboard에서 Blueprint를
직접 sync하면 **유료 Web Service, Postgres, persistent disk가 생성**되므로 가격과
결제수단을 먼저 확인해야 합니다.

## 구성

```text
Internet
  -> Render Web Service (FastAPI, one instance / one Uvicorn worker)
       -> Render Postgres (workflow와 Demand source of truth)
       -> /var/data persistent disk (BGE cache와 embedded Chroma index)
       -> S3-compatible object storage (Passport Evidence)
```

- `preDeployCommand: alembic upgrade head`가 새 release 전에 DB migration을 실행합니다.
- 저장소 기본 branch `main`에는 아직 이 backend가 없으므로 Blueprint와 Web Service 모두
  `dev`를 명시합니다. 운영 승격 후에는 검증된 `main` commit으로 함께 변경합니다.
- build는 Python 3.12.11을 고정하고 `scripts/install_match_runtime.sh`를 실행합니다. 이
  script는 공식 PyTorch CPU index에서 torch 2.7.1을 먼저 설치한 뒤 BGE dependencies를
  설치하며, CUDA build가 들어오면 즉시 실패합니다.
- `startCommand`는 Render의 `$PORT`에 bind하고 worker를 1개로 고정합니다.
- Render의 자동 health check는 외부 S3 일시 장애가 유일한 BGE instance를 재시작하지 않도록
  `/health/live`를 사용합니다. `/health/ready`는 DB, BGE/Chroma, Evidence bucket을 확인하는
  수동·외부 deep probe입니다.
- Render Postgres의 `connectionString`은 `postgresql://` 형식입니다. 애플리케이션이
  설치된 psycopg v3 driver에 맞춰 `postgresql+psycopg://`로 정규화합니다.
- production에서는 Demo seed/reset/auth를 모두 끄고 API-key RBAC를 강제합니다.
- production Evidence는 `s3`만 허용하므로 Render의 ephemeral filesystem에 업로드를
  저장하는 실수를 시작 단계에서 차단합니다.

## 유료·용량 제약

현재 Blueprint는 실제 BGE runtime을 선택하므로 `pro plus`(8 GB RAM), 10 GB
persistent disk, `basic-1gb` Postgres를 명시합니다. 이는 시작 구성이지 성능 보장이
아닙니다. BGE-M3 모델 파일, Python/torch runtime, embedding 작업이 함께 메모리를
사용하므로 실제 Golden flow와 부하 테스트 결과에 따라 상향해야 합니다.

일반 PyPI resolution에서 CPU 실행 설정만 바꾸는 것으로는 CUDA/NVIDIA wheel 다운로드를
막을 수 없습니다. 그래서 CPU wheel을 선설치하고 `torch.version.cuda is None`을 build에서
검사합니다. PyTorch 공식 index에는 torch 2.7.1의 CPython 3.12 manylinux 2.28 wheel이
x86_64와 aarch64 모두 제공됩니다. Render native Python runtime은 Debian 12 계열이지만,
실제 Render build 자체는 아직 실행하지 않았습니다. 첫 build에서 wheel 선택, 설치 용량,
`pip check` 출력까지 확인해야 하며 실패하면 유료 배포를 계속하지 않습니다.

Render 공식 문서에 따르면 persistent disk는 유료 서비스에만 붙일 수 있고 한 service
instance만 접근할 수 있습니다. disk가 있으면 multi-instance scale과 zero-downtime
deploy를 사용할 수 없고, build/pre-deploy에서도 disk에 접근할 수 없습니다. 따라서:

- Alembic은 disk가 아니라 managed Postgres만 사용합니다.
- BGE cache와 Chroma는 start/runtime에 `/var/data`를 사용합니다.
- Web Service instance와 Uvicorn worker를 각각 1개로 유지합니다.
- 배포 교체 중 수 초의 중단 가능성을 허용하는 MVP 구성입니다.

disk는 build와 pre-deploy에서 보이지 않으므로 BGE weights를 그 단계에서 미리 받을 수
없습니다. 최초 start에서 약 4.59 GB 모델을 `/var/data/huggingface`에 cold download한 뒤
CPU에 load하고 Chroma를 확인합니다. 이 동안 `/health/ready`는 응답할 수 없으며 네트워크
속도와 메모리에 따라 수 분 이상 걸릴 수 있습니다. Render의 start command 제한은 15분이므로
그 안에 startup이 끝나지 않거나 8 GB RAM으로 부족하면 최초 배포가 실패할 수 있습니다.
그 경우 로그와 실제 peak RAM을 근거로 plan을 상향한 뒤 다시 검증해야 합니다. 모델 cache가
disk에 생긴 뒤의 재시작은 download를 재사용하지만, disk가 붙은 배포 자체에는 짧은 downtime이
있습니다. 즉 `pro plus`와 10 GB disk는 최소 실험안이지 성능·비용 보장이 아닙니다.

2026-08-18 로컬 ARM Docker 격리 검증에서는 최초 4.3 GB cache 완성과 Golden E2E까지 약
17분 20초가 걸렸고 cold-download 과정 peak RAM은 약 5.10 GiB였습니다. 같은 cache를
CPU-only 이미지에서 재사용한 뒤에는 startup 7.39초, restart→ready 10.76초, peak 약
914 MiB였으며 Top-3 Match는 0.18초였습니다. CPU-only image는 약 406 MB로 일반 PyPI가
CUDA dependencies를 포함한 비교 image 약 3.16 GB보다 87% 작았습니다. 이 수치는 로컬
네트워크·ARM·DEMO Demand 3건의 관측값이지 Render x86 성능 보장이 아닙니다. 특히 관측 cold
시간이 Render start 제한 15분보다 길었으므로 첫 유료 배포에서는 로그를 관찰하고, 실패하면
부분 cache 재사용 가능 여부·plan 또는 별도 모델 serving 구조를 검토해야 합니다.

Evidence는 Chroma disk와 수명·복구 요구사항이 다르므로 S3-compatible object storage에
저장합니다. AWS S3나 Cloudflare R2 같은 provider의 bucket과 credential은 별도로
준비해야 하며 이 저장소에는 credential을 커밋하지 않습니다. production custom endpoint는
HTTPS만 허용합니다. 애플리케이션 시작 시 bucket 접근과 지정 prefix 아래 임시 object의
Put/Get/Delete를 한 번 검증하고 즉시 삭제합니다. connect 3초, read 10초, 총 2회 시도로
외부 storage 장애가 API worker와 DB pool을 장시간 점유하지 않게 제한합니다.

Evidence upload는 object 저장을 DB transaction·Case row lock 밖에서 수행한 뒤 상태를 다시
잠가 metadata와 Audit를 기록합니다. 최종 DB commit이 실패하면 object를 best-effort로
삭제합니다. 다운로드는 최대 25 MiB object 전체의 size와 SHA-256을 확인한 뒤에만 응답하고
`private, no-store`와 `nosniff` header를 설정합니다. 프로세스가 object 저장 직후 강제 종료되는
경우의 orphan은 여전히 가능하므로 bucket lifecycle rule과 정기 prefix/metadata reconciler를
운영 전에 마련해야 합니다. malware scan, KMS/retention 정책도 별도 운영 항목입니다.

## Blueprint 생성 시 입력할 secret

Render는 `sync: false` 값을 최초 Blueprint 생성 화면에서만 요청합니다. 기존 Blueprint에
secret 변수를 나중에 추가하면 Dashboard에서 직접 설정해야 합니다.

| 변수 | 입력 형식 |
| --- | --- |
| `API_KEY_CREDENTIALS` | key ID, secret SHA-256, actor, role의 JSON array |
| `CORS_ORIGINS` | 실제 Frontend origin의 JSON array. 예: `["https://app.example.com"]` |
| `EVIDENCE_S3_BUCKET` | private bucket 이름 |
| `EVIDENCE_S3_REGION` | AWS region 또는 provider 권장 값 |
| `EVIDENCE_S3_ENDPOINT_URL` | AWS S3는 provider 기본 endpoint, R2 등은 S3 API endpoint |
| `EVIDENCE_S3_ACCESS_KEY_ID` | server-side object credential |
| `EVIDENCE_S3_SECRET_ACCESS_KEY` | server-side object credential |

평문 API key를 `API_KEY_CREDENTIALS`에 넣지 않습니다. 예를 들어 로컬에서 secret의
SHA-256을 만든 뒤 그 digest만 JSON에 넣습니다.

```bash
python -c 'import getpass,hashlib; print(hashlib.sha256(getpass.getpass().encode()).hexdigest())'
```

role은 `VIEWER`, `OPERATOR`, `DECISION_MAKER`, `ADMIN` 중 하나입니다. 실제 운영에는
최소한 operator, decision maker, admin을 서로 다른 key로 발급합니다.

`EVIDENCE_S3_CONNECT_TIMEOUT_SECONDS=3`, `EVIDENCE_S3_READ_TIMEOUT_SECONDS=10`,
`EVIDENCE_S3_MAX_ATTEMPTS=2`는 secret이 아닌 안전 기본값이며 Blueprint에서 생략해도
애플리케이션 기본값이 적용됩니다. 운영 측정으로 바꿀 때만 일반 환경변수로 명시합니다.

## 배포 순서

1. Render 가격, Web/Postgres/disk plan과 외부 object-storage 비용을 확인합니다.
2. private S3-compatible bucket과 최소권한 credential을 만듭니다. AWS S3 기준
   `s3:ListBucket`과 `greenfab/production/evidence/*`의 Put/Get/Delete를 허용해야
   HeadBucket 및 startup canary가 통과합니다. R2 등은 같은 API 동작에 필요한 provider별
   최소권한을 적용합니다.
3. CI가 SHA-256으로 고정한 Render 공식 JSON Schema를 통과했는지 확인하고, 활성 Render
   workspace가 있는 운영자 환경에서 `render blueprints validate render.yaml`로 schema 외
   plan·region·resource reference 의미 검증도 다시 실행합니다.
4. Render Dashboard에서 저장소의 `render.yaml`을 Blueprint로 연결합니다.
5. 위 `sync: false` 값을 입력하고 최초 배포를 시작합니다.
6. pre-deploy의 `alembic upgrade head` 성공을 확인합니다.
7. Render 자동 probe가 `/health/live`인지 확인하고 `/health/ready`도 직접 호출합니다. ready 응답의 provider는
   `BgeChromaMatchProvider`, storage는 `S3EvidenceStorage`여야 합니다.
8. 운영 Demand를 등록하고 index sync event가 `SUCCEEDED`인지 확인합니다.
9. Golden workflow, `422`, `409`, `503`, idempotency를 외부 URL에서 재검증합니다.

Production은 `SEED_DEMO_DATA=false`이므로 최초 DB가 비어 있는 것이 정상입니다. 실제
Detect artifact와 Demand를 승인된 운영 절차로 등록하기 전에는 사용자 workflow가
완성되지 않습니다.

## 최초 데이터 provisioning

### 1. Detect artifact

실제 `dashboard_data.json`은 Git에 넣거나 public URL에서 받지 않습니다. 현재 CLI는 로컬
파일을 hash·schema 검증하고 같은 byte artifact 재실행을 idempotent하게 처리합니다. 이
Blueprint에는 persistent disk가 있으므로 다음 운영 절차를 사용합니다.

1. Render Dashboard의 SSH 명령을 확인하고 SCP/SFTP로 승인된 artifact를
   `/var/data/imports/<release-id>/dashboard_data.json`에 전송합니다.
2. **실행 중인 Web Service의 Shell**에서 아래 명령을 실행합니다. disk는 one-off job에서
   보이지 않으므로, SCP로 보낸 파일을 one-off command에서 import하면 안 됩니다.
3. 출력의 `artifact_sha256`, 생성·갱신 Case 수를 원본 pipeline manifest와 대조합니다.
4. 보존 정책에 따라 원본을 private object storage로 archive하고 disk 임시본을 정리합니다.

```bash
python -m app.cli.import_detect \
  /var/data/imports/<release-id>/dashboard_data.json \
  --source-type REAL \
  --actor pipeline_operator
```

저장소에 포함된 `data/outputs/detect/dashboard_data.json`은 DEMO 검증 자료입니다. 이를
`REAL`로 import하지 않습니다. 운영 artifact가 아직 없다면 production DB를 비워 둔 채
인프라 health만 확인해야 합니다.

### 2. Demand 최소 3건

Demand는 PostgreSQL이 source of truth이고 등록 API가 성공한 뒤 같은 요청에서 embedded
Chroma를 upsert합니다. 시작 sync는 version/content hash가 같은 문서는 다시 embedding하지 않고
변경·누락 문서와 stale ID만 reconcile합니다. crash로 남은 PENDING event는 시작 시 FAILED로
표시된 뒤 새 SYNC_ALL event가 수행됩니다. `ADMIN` API key로 실제 수요처가 검증한 Demand를 최소 3건 등록합니다.
key를 command history나 파일에 저장하지 않습니다.

```bash
read -s GREENFAB_ADMIN_KEY
curl -fsS -X POST "https://<api-host>/api/v1/demands" \
  -H "X-API-Key: ${GREENFAB_ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  --data @approved-demand-01.json
unset GREENFAB_ADMIN_KEY
```

`approved-demand-01.json`은 `docs/api-contract.md`의 DemandCreate 계약을 따라야 하며
`source_type=REAL`은 실제 수요처 확인 근거가 있을 때만 사용합니다. 나머지 Demand도 같은
방식으로 등록한 뒤 전체 reconcile과 event 확인을 수행합니다.

```bash
read -s GREENFAB_ADMIN_KEY
curl -fsS -X POST "https://<api-host>/api/v1/demands/index/sync" \
  -H "X-API-Key: ${GREENFAB_ADMIN_KEY}"
curl -fsS "https://<api-host>/api/v1/demands/index/events?limit=20" \
  -H "X-API-Key: ${GREENFAB_ADMIN_KEY}"
unset GREENFAB_ADMIN_KEY
```

모든 대상 event가 `SUCCEEDED`이고 `/health/ready`의 Match provider가
`BgeChromaMatchProvider`일 때만 API matching 검증을 시작합니다.

## Mock 선택 시 주의

`MATCH_PROVIDER=mock`은 인프라/API smoke test와 고정 Golden DEMO snapshot을 위한
provider입니다. 임의 Passport를 semantic search하는 실제 BGE 실행이 아닙니다. Mock을
선택할 때는 build command에서 `match` extra와 BGE/Chroma용 disk를 제거할 수 있지만,
이를 실제 AI matching이 배포된 것으로 발표하면 안 됩니다. 반대로 현재 Blueprint의
`bge_chroma`는 dependency/model/index가 준비되지 않으면 시작과 readiness가 실패하며
Mock으로 자동 전환하지 않습니다.

## 공식 Render 근거 (2026-08-18 확인)

- Blueprint fields, `fromDatabase`, `sync: false`, `preDeployCommand`, `healthCheckPath`:
  <https://render.com/docs/blueprint-spec>
- FastAPI `$PORT` bind 방식: <https://render.com/docs/deploy-fastapi>
- build/pre-deploy/start 순서와 timeout, ephemeral filesystem:
  <https://render.com/docs/deploys>
- persistent disk의 유료·single-instance·pre-deploy 접근 불가·zero-downtime 제한:
  <https://render.com/docs/disks>
- Render instance RAM 표: <https://render.com/docs/compute-plans>
- Render Python version 고정 방식: <https://render.com/docs/python-version>
- Managed Postgres internal URL, same-region private network, external access 차단:
  <https://render.com/docs/postgresql-creating-connecting>
- Blueprint 공식 JSON Schema: <https://render.com/schema/render.yaml.json>
- PyTorch 공식 CPU wheel 설치 명령과 2.7.1 CPU wheel index:
  <https://pytorch.org/get-started/previous-versions/>,
  <https://download.pytorch.org/whl/cpu/torch/>
- Botocore timeout/retry configuration:
  <https://docs.aws.amazon.com/botocore/latest/reference/config.html>
- AWS S3 API별 최소권한 매핑:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-policy-actions.html>
- Cloudflare R2 Boto3 endpoint/credential 구성:
  <https://developers.cloudflare.com/r2/examples/aws/boto3/>
