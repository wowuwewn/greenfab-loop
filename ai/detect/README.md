# SECOM Detect 재현 파이프라인

팀원이 전처리한 `secom_preprocessed.xlsx`에서 다음 산출물을 다시 만드는 코드입니다.

1. Logistic Regression, Random Forest, XGBoost, LightGBM 동일 outer fold 비교
2. outer-train 내부 OOF만 이용한 fold별 임계값 선택
3. 사전 정의된 평균 Precision 하한을 적용한 LightGBM 선정
4. 선정 모델의 OOF 점수·예측·상대 위험 순위
5. 각 행을 학습하지 않은 outer-fold 모델로 계산한 OOF SHAP
6. 행 순서 마지막 20% 보조 강건성 검증
7. `dashboard_data.json`, CSV, 분석 보고서와 로컬 추론 bundle 생성

## 데이터 계약

- 기본 입력: `data/real/secom_preprocessed.xlsx`
- 시트: `SECOM_Data`
- 라벨: `result`
- 예상 크기: 1,567행, 라벨 1개와 센서 446개
- 예상 분포: 정상 1,463건, 불량 104건
- 검증한 입력 SHA-256: `196cea8a01998f0d951e1d76a94f5561b778833ac907d186bc8a90078aa1f377`

Excel은 저장소에 포함하지 않습니다. 팀 공유 파일을 `data/real/`에 두거나 `--input`으로 로컬 경로를 지정하세요.

원 데이터 출처는 Michael McCann과 Adrian Johnston의 UCI SECOM 데이터셋입니다.

- UCI: https://archive.ics.uci.edu/dataset/179/secom
- DOI: https://doi.org/10.24432/C54305
- License: CC BY 4.0

## 실행

Python 3.12 이상을 권장합니다. 참조 산출물은 Python 3.14.6과 `requirements.txt`의 고정 버전으로 생성했습니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r ai/detect/requirements.txt

python ai/detect/run_pipeline.py \
  --input /path/to/secom_preprocessed.xlsx \
  --expected-input-sha256 196cea8a01998f0d951e1d76a94f5561b778833ac907d186bc8a90078aa1f377 \
  --output-dir data/outputs/detect
```

Apple Silicon에서 LightGBM이 `libomp` 오류를 내면 `brew install libomp` 후 다시 실행하세요.

빠른 설치·CLI 점검에서는 `--models lr --outer-folds 2 --inner-folds 2 --skip-shap --no-time-holdout`을 사용할 수 있습니다. 이 결과를 최종 지표로 사용하면 안 됩니다.

## 생성 파일

| 파일 | 용도 | Git 커밋 여부 |
|---|---|---|
| `dashboard_data.json` | 기존 Insight 프런트의 검증 수치 원천 | 참조본만 커밋 |
| `run_metadata.json` | 입력 해시·패키지·실행 설정 | 필요 시 공유 |
| `model_comparison.csv` | 동일 fold 모델 비교 | 필요 시 공유 |
| `fold_metrics.csv` | 모델·fold별 임계값과 성능 | 필요 시 공유 |
| `oof_predictions.csv` | 행별 OOF 점수·예측·위험순위 | 민감도 확인 후 공유 |
| `top_features.csv` | global OOF SHAP 상위 센서 | 필요 시 공유 |
| `risk_top30.csv` | 상위 위험 건 요약 | 필요 시 공유 |
| `temporal_holdout.json` | 행 순서 기반 보조 검증 | 필요 시 공유 |
| `analysis_report.md` | 방법·결과·한계 요약 | 필요 시 공유 |
| `selected_model_bundle.joblib` | 로컬 추론용 임시 모델 | 커밋하지 않음 |

`joblib` 파일은 Python 객체 역직렬화를 사용합니다. 이 파이프라인에서 직접 만든 파일만 로드하고, 출처를 신뢰할 수 없는 bundle은 열지 마세요.

`data/outputs/detect/dashboard_data.json`은 검증된 입력과 참조 환경으로 만든 고정 산출물입니다. 이 파일은 Loop Data Contract의 최상위 envelope가 아니라 기존 Insight 분석 화면용 결과입니다. Loop에서는 Detect 단계의 `case` 데이터로 변환해서 사용해야 합니다.

기존 호환 JSON의 `scenario_defaults`는 화면 데모용 사용자 입력값이며 SECOM이나 Detect 모델이 산출한 값이 아닙니다. Loop ESG Scenario로 옮길 때는 `source_type: SCENARIO`, 계수 출처와 공식 버전을 별도로 확정해야 합니다.

## 검증

```bash
python -m unittest discover -s ai/detect/tests -v
python -m py_compile ai/detect/run_pipeline.py
python ai/detect/verify_reference.py \
  --actual data/outputs/detect/dashboard_data.json
```

참조 실행에서 확인된 핵심 결과:

- 선정 모델: LightGBM
- pooled OOF Recall: `0.4711538462`
- pooled OOF Precision: `0.1666666667`
- pooled OOF F1: `0.2462311558`
- pooled OOF Balanced Accuracy: `0.6518448657`
- outer-fold 평균 PR-AUC: `0.1883620556`
- 기존 프런트 참조 JSON SHA-256: `2d9f8dd5963d2804080ffbd83153ae604cd4430842721524e2e79fe2ece3813c` (파일 끝 개행 제외)

패키지·플랫폼 차이로 마지막 부동소수점 자릿수가 달라질 수 있으므로 핵심 지표는 허용오차와 함께 비교합니다. 모델명, fold 수, 표본 수, 혼동행렬 합계, 위험 등급 합계는 정확히 일치해야 합니다.

고정 버전 전체 재실행에서는 모든 구조와 지표가 참조본과 일치했고, Random Forest 임계값 중앙값 한 곳만 약 `2e-17` 차이가 발생했습니다. `verify_reference.py`는 이러한 부동소수점 차이만 허용하고 키·배열 순서·문자열·의미 있는 수치 차이는 실패 처리합니다.

## 해석상 제한

- Excel은 팀원이 전체 표본 중앙값으로 이미 결측치를 대체한 자료입니다. 스크립트 안의 전처리는 fold 내부에서 수행하지만, 원자료부터 완전히 누수를 차단한 검증은 아닙니다.
- 네 모델을 같은 CV 결과로 선택하고 그 성능을 보고하므로 완전한 nested model-selection 추정치는 아닙니다.
- raw score는 보정된 불량 확률이 아닙니다. 대시보드 순위는 fold 내부 상대 백분위입니다.
- fold별 최고 백분위처럼 동점이 발생할 수 있습니다. `risk_rank`는 화면의 결정적 표시 순서이며 과학적인 단독 순위로 해석하면 안 됩니다.
- SHAP은 익명 센서의 모델 기여도이며 물리적 불량 원인이나 인과효과가 아닙니다.
- Tree SHAP 기여값은 모델의 원시 출력 척도이며 확률 퍼센트가 아닙니다.
- timestamp가 없어 마지막 20% 검증은 정식 시간 외부검증이 아니라 행 순서 보존 가정의 보조 점검입니다.
- 최종 프런트용 결과에서는 `--no-time-holdout`과 일부 모델만 실행하는 `--models` 축약 옵션을 사용하지 마세요. 해당 옵션은 설치 점검용이며 프런트가 기대하는 필드를 비울 수 있습니다.
- SECOM은 생산 위험 신호만 제공합니다. 자원 발생, 자원 종류·수량, 재사용 적합성과 ESG 효과를 예측하지 않습니다.
