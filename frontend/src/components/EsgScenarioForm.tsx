import { useState } from 'react'
import { ArrowRight, Calculator } from 'lucide-react'
import { toApiError, type ApiError } from '../api/client'
import type { EsgScenario } from '../types/loop'
import { ApiErrorMessage } from './ApiErrorMessage'

interface EsgScenarioFormProps {
  esgScenario: EsgScenario | null
  isBusy: boolean
  onGenerate: () => Promise<void>
}

const DEMO_ESG_COMPARISON = {
  baselinePath: '기존 폐기 처리',
  selectedPath: '세라믹 원료 파일럿 활용',
  energyDifference: '변화 없음',
  energyContext: '기존 처리 대비',
  carbonDifference: 2400,
  carbonUnit: 'kgCO₂e',
  carbonContext: '기존 처리 대비 증가',
  sourceType: 'SCENARIO',
  dataOrigin: 'Frontend DEMO 표시 가정',
} as const

const formatQuantity = (value: number | null, unit: string | null) => {
  if (value === null) return '수량 미확인'
  const formatted = new Intl.NumberFormat('ko-KR', {
    maximumFractionDigits: 3,
  }).format(value)
  return `${formatted}${unit ? ` ${unit}` : ''}`
}

const formatSignedMeasurement = (value: number, unit: string) => {
  const formatted = new Intl.NumberFormat('ko-KR').format(value)
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${formatted} ${unit}`
}

const decisionLabel = {
  APPROVED: '승인',
  HOLD: '보류',
  REJECTED: '거절',
} as const

export function EsgScenarioForm({
  esgScenario,
  isBusy,
  onGenerate,
}: EsgScenarioFormProps) {
  const [apiError, setApiError] = useState<ApiError | null>(null)

  const generate = async () => {
    setApiError(null)
    try {
      await onGenerate()
    } catch (error) {
      setApiError(toApiError(error))
    }
  }

  if (!esgScenario) {
    return (
      <div className="esg-scenario-content">
        <div className="esg-form">
          <div className="esg-results__status">
            <Calculator size={18} strokeWidth={1.9} aria-hidden="true" />
            <strong>
              저장된 Passport와 사람의 Decision으로 시나리오를 생성합니다.
            </strong>
          </div>
          <p className="esg-scenario-notice">
            Backend는 승인된 후보 전환 가능량만 계산합니다. 에너지·탄소 예상
            차이는 생성 후 DEMO/SCENARIO 표시 가정으로 분리해 보여줍니다.
          </p>
          <ApiErrorMessage
            error={apiError}
            onRetry={generate}
            retryDisabled={isBusy}
          />
          <button
            className="primary-button esg-calculate-button"
            type="button"
            onClick={() => void generate()}
            disabled={isBusy}
          >
            {isBusy ? '시나리오 생성 중…' : 'ESG 시나리오 생성'}
            <ArrowRight size={17} strokeWidth={1.9} aria-hidden="true" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="esg-scenario-content">
      <div className="esg-comparison" aria-live="polite">
        <header className="esg-comparison__header">
          <span className="esg-comparison__badge">
            {DEMO_ESG_COMPARISON.sourceType}
          </span>
          <div>
            <h3>ESG 시나리오 비교 완료</h3>
            <p>
              사용자 입력값과 데모 가정을 기준으로 기존 처리와 선택 경로를
              비교합니다.
            </p>
          </div>
        </header>

        <div className="esg-path-comparison" aria-label="기존 경로와 선택 경로 비교">
          <div className="esg-path-option">
            <span>기존 경로</span>
            <strong>{DEMO_ESG_COMPARISON.baselinePath}</strong>
          </div>
          <span className="esg-path-comparison__arrow" aria-hidden="true">
            <ArrowRight size={18} strokeWidth={1.8} />
          </span>
          <div className="esg-path-option esg-path-option--selected">
            <span>선택 경로</span>
            <strong>{DEMO_ESG_COMPARISON.selectedPath}</strong>
          </div>
        </div>

        <dl className="esg-impact-summary">
          <div>
            <dt>시나리오 적용 자원량</dt>
            <dd>
              {formatQuantity(
                esgScenario.inputs.resource_quantity,
                esgScenario.inputs.unit,
              )}
            </dd>
            <small>저장된 Passport 입력값</small>
          </div>
          <div>
            <dt>예상 에너지 차이</dt>
            <dd>{DEMO_ESG_COMPARISON.energyDifference}</dd>
            <small>{DEMO_ESG_COMPARISON.energyContext}</small>
          </div>
          <div className="is-tradeoff">
            <dt>예상 탄소 차이</dt>
            <dd>
              {formatSignedMeasurement(
                DEMO_ESG_COMPARISON.carbonDifference,
                DEMO_ESG_COMPARISON.carbonUnit,
              )}
            </dd>
            <small>{DEMO_ESG_COMPARISON.carbonContext}</small>
          </div>
        </dl>

        <section className="esg-decision-guidance" aria-labelledby="esg-guidance-title">
          <h4 id="esg-guidance-title">
            순환이 항상 환경적으로 더 유리한 것은 아닙니다.
          </h4>
          <p>
            이 시나리오에서는 자원 활용 경로를 변경할 경우 예상 탄소 영향이
            증가합니다. 담당자는 자원순환 가능성뿐 아니라 환경적 차이도 함께
            검토해 최종 경로를 결정할 수 있습니다.
          </p>
        </section>

        <div className="esg-scenario-disclaimer">
          <strong>SCENARIO · 실제 환경 성과가 아닙니다.</strong>
          <p>
            표시된 값은 AI 예측값이 아니라 사용자 입력값과 데모 가정을 기반으로
            한 시나리오 비교값입니다.
          </p>
          <small>
            에너지·탄소 예상 차이는 Frontend DEMO/SCENARIO 표시 가정이며 서버
            계산 결과가 아닙니다.
          </small>
        </div>

        <details className="esg-calculation-info">
          <summary>계산 정보</summary>
          <dl>
            <div>
              <dt>비교 표시값 출처</dt>
              <dd>{DEMO_ESG_COMPARISON.dataOrigin}</dd>
            </div>
            <div>
              <dt>서버 후보 전환 가능량</dt>
              <dd>
                {formatQuantity(
                  esgScenario.results.candidate_diversion_quantity,
                  esgScenario.results.unit,
                )}
              </dd>
            </div>
            <div>
              <dt>사람의 Decision</dt>
              <dd>{decisionLabel[esgScenario.inputs.decision_status]}</dd>
            </div>
            <div>
              <dt>계산식 버전</dt>
              <dd>{esgScenario.formula_version ?? '기록 없음'}</dd>
            </div>
            <div>
              <dt>외부 검증 계수</dt>
              <dd>{esgScenario.factor_source ?? '사용하지 않음'}</dd>
            </div>
          </dl>
        </details>
      </div>
    </div>
  )
}
