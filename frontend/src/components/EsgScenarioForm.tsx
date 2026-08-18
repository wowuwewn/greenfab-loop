import { useState } from 'react'
import { ArrowRight, Calculator, CheckCircle2 } from 'lucide-react'
import { toApiError, type ApiError } from '../api/client'
import type { EsgScenario } from '../types/loop'
import { ApiErrorMessage } from './ApiErrorMessage'

interface EsgScenarioFormProps {
  esgScenario: EsgScenario | null
  isBusy: boolean
  onGenerate: () => Promise<void>
}

const formatQuantity = (value: number | null, unit: string | null) => {
  if (value === null) return '수량 미확인'
  const formatted = new Intl.NumberFormat('ko-KR', {
    maximumFractionDigits: 3,
  }).format(value)
  return `${formatted}${unit ? ` ${unit}` : ''}`
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
            현재 MVP는 승인된 후보 자원량만 계산합니다. 탄소·전력 절감량이나
            검증된 환경 성과를 계산하지 않습니다.
          </p>
          <ApiErrorMessage error={apiError} onRetry={generate} retryDisabled={isBusy} />
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
      <div className="esg-results" aria-live="polite">
        <div className="esg-results__status">
          <CheckCircle2 size={17} strokeWidth={2} aria-hidden="true" />
          <strong>서버 시나리오 생성 완료</strong>
        </div>
        <div className="esg-pathway-flow">
          <span>Passport 자원량</span>
          <ArrowRight size={14} aria-hidden="true" />
          <span>
            사람의 {decisionLabel[esgScenario.inputs.decision_status]} 결정
          </span>
          <strong>후보 전환 가능량</strong>
        </div>
        <dl className="esg-result-summary">
          <div>
            <dt>입력 자원량</dt>
            <dd>
              {formatQuantity(
                esgScenario.inputs.resource_quantity,
                esgScenario.inputs.unit,
              )}
            </dd>
          </div>
          <div>
            <dt>후보 전환 가능량</dt>
            <dd>
              {formatQuantity(
                esgScenario.results.candidate_diversion_quantity,
                esgScenario.results.unit,
              )}
            </dd>
          </div>
          <div>
            <dt>데이터 구분</dt>
            <dd>{esgScenario.source_type}</dd>
          </div>
        </dl>
        <div className="esg-result-meta">
          <span>
            계산식 버전
            <strong>{esgScenario.formula_version ?? '기록 없음'}</strong>
          </span>
          <span>
            외부 검증 계수
            <strong>{esgScenario.factor_source ?? '사용하지 않음'}</strong>
          </span>
        </div>
        <p className="esg-scenario-notice">
          이 값은 후보 자원량 시나리오이며 실제 인계, 폐기물 감축 또는 탄소
          감축 실적이 아닙니다.
        </p>
      </div>
    </div>
  )
}
