import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, Calculator, ChevronDown } from 'lucide-react'
import { toApiError, type ApiError } from '../api/client'
import { ApiErrorMessage } from './ApiErrorMessage'
import type {
  DecisionStatus,
  EsgScenario,
  MatchCandidate,
} from '../types/loop'

interface EsgScenarioFormProps {
  esgScenario: EsgScenario | null
  defaultQuantityKg?: number | null
  selectedCandidate?: MatchCandidate | null
  decisionStatus?: DecisionStatus | null
  onCalculate: (scenario: EsgScenario) => Promise<void>
}

interface EsgFormValues {
  scenario_quantity_kg: string
  baseline_pathway: string
  alternative_pathway: string
  baseline_energy_factor_kwh_per_kg: string
  alternative_energy_factor_kwh_per_kg: string
  baseline_carbon_factor_kgco2e_per_kg: string
  alternative_carbon_factor_kgco2e_per_kg: string
  factor_source: string
}

type EsgFormErrors = Partial<Record<keyof EsgFormValues, string>>

const BASELINE_OPTIONS = [
  '기존 폐기 처리',
  '소각',
  '매립',
  '외부 폐기물 처리',
]

const compactAlternativeLabel = (candidate: MatchCandidate | null) => {
  if (!candidate) return null
  if (candidate.demand_id === 'D01') return '세라믹 원료 파일럿 활용'
  if (candidate.demand_id === 'D15') return '시험용 보조 원료 파일럿 활용'
  return '선택 후보 기반 파일럿 활용'
}

const initialValues = (
  scenario: EsgScenario | null,
  defaultQuantityKg: number | null | undefined,
  defaultAlternativePathway: string,
): EsgFormValues => ({
  scenario_quantity_kg: scenario
    ? String(scenario.inputs.scenario_quantity_kg)
    : defaultQuantityKg !== null &&
        defaultQuantityKg !== undefined &&
        Number.isFinite(defaultQuantityKg) &&
        defaultQuantityKg > 0
      ? String(defaultQuantityKg)
      : '',
  baseline_pathway: scenario?.inputs.baseline_pathway ?? '기존 폐기 처리',
  alternative_pathway:
    scenario?.inputs.alternative_pathway ?? defaultAlternativePathway,
  baseline_energy_factor_kwh_per_kg:
    scenario?.inputs.baseline_energy_factor_kwh_per_kg === null || !scenario
      ? ''
      : String(scenario.inputs.baseline_energy_factor_kwh_per_kg),
  alternative_energy_factor_kwh_per_kg:
    scenario?.inputs.alternative_energy_factor_kwh_per_kg === null || !scenario
      ? ''
      : String(scenario.inputs.alternative_energy_factor_kwh_per_kg),
  baseline_carbon_factor_kgco2e_per_kg:
    scenario?.inputs.baseline_carbon_factor_kgco2e_per_kg === null || !scenario
      ? ''
      : String(scenario.inputs.baseline_carbon_factor_kgco2e_per_kg),
  alternative_carbon_factor_kgco2e_per_kg:
    scenario?.inputs.alternative_carbon_factor_kgco2e_per_kg === null || !scenario
      ? ''
      : String(scenario.inputs.alternative_carbon_factor_kgco2e_per_kg),
  factor_source: scenario?.factor_source ?? '',
})

const formatNumber = (value: number) =>
  new Intl.NumberFormat('ko-KR', {
    maximumFractionDigits: 3,
  }).format(Math.abs(value) < 1e-10 ? 0 : value)

const formatDifference = (
  value: number | null,
  unit: 'kWh' | 'kgCO₂e',
) => {
  if (value === null) return '계수 미입력'
  if (Math.abs(value) < 1e-10) return '변화 없음'
  if (value > 0) return `${formatNumber(value)} ${unit} 감소`
  return `${formatNumber(Math.abs(value))} ${unit} 증가`
}

export function EsgScenarioForm({
  esgScenario,
  defaultQuantityKg = null,
  selectedCandidate = null,
  decisionStatus = null,
  onCalculate,
}: EsgScenarioFormProps) {
  const canUseSelectedCandidate =
    selectedCandidate !== null &&
    (decisionStatus === 'APPROVED' || decisionStatus === 'HOLD')
  const defaultAlternativePathway = selectedCandidate && canUseSelectedCandidate
    ? `${selectedCandidate.company_name} · ${selectedCandidate.demand_description}`
    : ''
  const alternativeDisplayLabel = compactAlternativeLabel(selectedCandidate)
  const [values, setValues] = useState<EsgFormValues>(() =>
    initialValues(esgScenario, defaultQuantityKg, defaultAlternativePathway),
  )
  const [errors, setErrors] = useState<EsgFormErrors>({})
  const [isCalculating, setIsCalculating] = useState(false)
  const [apiError, setApiError] = useState<ApiError | null>(null)
  const [isQuantityFromPassport, setIsQuantityFromPassport] = useState(
    () =>
      esgScenario === null &&
      defaultQuantityKg !== null &&
      Number.isFinite(defaultQuantityKg) &&
      defaultQuantityKg > 0,
  )
  const initialBaselinePathway =
    esgScenario?.inputs.baseline_pathway ?? '기존 폐기 처리'
  const [baselineOption, setBaselineOption] = useState(() =>
    BASELINE_OPTIONS.includes(initialBaselinePathway)
      ? initialBaselinePathway
      : '기타',
  )
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)

  const updateValue = (field: keyof EsgFormValues, value: string) => {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  const hasAnyFactorInput = [
    values.baseline_energy_factor_kwh_per_kg,
    values.alternative_energy_factor_kwh_per_kg,
    values.baseline_carbon_factor_kgco2e_per_kg,
    values.alternative_carbon_factor_kgco2e_per_kg,
  ].some((value) => value.trim() !== '')

  const parseOptionalFactor = (
    field: keyof Pick<
      EsgFormValues,
      | 'baseline_energy_factor_kwh_per_kg'
      | 'alternative_energy_factor_kwh_per_kg'
      | 'baseline_carbon_factor_kgco2e_per_kg'
      | 'alternative_carbon_factor_kgco2e_per_kg'
    >,
    nextErrors: EsgFormErrors,
  ) => {
    const rawValue = values[field].trim()
    if (!rawValue) return null

    const parsedValue = Number(rawValue)
    if (!Number.isFinite(parsedValue)) {
      nextErrors[field] = '숫자로 입력해주세요.'
      return null
    }
    if (parsedValue < 0) {
      nextErrors[field] = '0 이상의 숫자로 입력해주세요.'
      return null
    }

    return parsedValue
  }

  const calculateScenario = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const nextErrors: EsgFormErrors = {}
    const quantity = Number(values.scenario_quantity_kg)
    const baselinePathway = values.baseline_pathway.trim()
    const alternativePathway = values.alternative_pathway.trim()

    if (!values.scenario_quantity_kg.trim()) {
      nextErrors.scenario_quantity_kg = '비교할 자원량을 입력해주세요.'
    } else if (!Number.isFinite(quantity) || quantity <= 0) {
      nextErrors.scenario_quantity_kg = '0보다 큰 숫자를 입력해주세요.'
    }

    if (!baselinePathway) {
      nextErrors.baseline_pathway = '현재 처리 방식을 입력해주세요.'
    }

    if (!alternativePathway) {
      nextErrors.alternative_pathway = '대안 활용 방식을 입력해주세요.'
    }

    const baselineEnergyFactor = parseOptionalFactor(
      'baseline_energy_factor_kwh_per_kg',
      nextErrors,
    )
    const alternativeEnergyFactor = parseOptionalFactor(
      'alternative_energy_factor_kwh_per_kg',
      nextErrors,
    )
    const baselineCarbonFactor = parseOptionalFactor(
      'baseline_carbon_factor_kgco2e_per_kg',
      nextErrors,
    )
    const alternativeCarbonFactor = parseOptionalFactor(
      'alternative_carbon_factor_kgco2e_per_kg',
      nextErrors,
    )
    if (hasAnyFactorInput && !values.factor_source.trim()) {
      nextErrors.factor_source = '입력한 계수의 출처를 함께 기록해주세요.'
      setIsDetailsOpen(true)
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }

    const energyDifference =
      baselineEnergyFactor !== null && alternativeEnergyFactor !== null
        ? quantity * (baselineEnergyFactor - alternativeEnergyFactor)
        : null
    const carbonDifference =
      baselineCarbonFactor !== null && alternativeCarbonFactor !== null
        ? quantity * (baselineCarbonFactor - alternativeCarbonFactor)
        : null

    setIsCalculating(true)
    setApiError(null)

    try {
      await onCalculate({
        source_type: 'SCENARIO',
        inputs: {
          scenario_quantity_kg: quantity,
          baseline_pathway: baselinePathway,
          alternative_pathway: alternativePathway,
          baseline_energy_factor_kwh_per_kg: baselineEnergyFactor,
          alternative_energy_factor_kwh_per_kg: alternativeEnergyFactor,
          baseline_carbon_factor_kgco2e_per_kg: baselineCarbonFactor,
          alternative_carbon_factor_kgco2e_per_kg: alternativeCarbonFactor,
        },
        results: {
          diverted_quantity_kg: quantity,
          energy_difference_kwh: energyDifference,
          carbon_difference_kgco2e: carbonDifference,
        },
        formula_version: 'ESG-SCENARIO-v0.1',
        factor_source: values.factor_source.trim() || null,
      })
      setErrors({})
    } catch (error) {
      setApiError(toApiError(error))
    } finally {
      setIsCalculating(false)
    }
  }

  return (
    <div className="esg-scenario-content">
      <form className="esg-form" onSubmit={calculateScenario} noValidate>
        <div className="esg-form__intro">
          <strong>앞 단계에서 확인한 정보로 비교 기준을 구성했습니다.</strong>
          <p>현재 처리 방식만 확인하고, 필요한 경우 자원량과 대안 가정을 수정할 수 있습니다.</p>
        </div>

        <div className="esg-scenario-overview">
          <label className="esg-field esg-quantity-field">
            <span><b className="esg-field-index">1</b> 자원량 <em>필수</em></span>
            <span className={`esg-input-with-unit${errors.scenario_quantity_kg ? ' is-error' : ''}`}>
              <input
                type="number"
                min="0"
                step="any"
                inputMode="decimal"
                value={values.scenario_quantity_kg}
                onChange={(event) => {
                  setIsQuantityFromPassport(false)
                  updateValue('scenario_quantity_kg', event.target.value)
                }}
                aria-invalid={Boolean(errors.scenario_quantity_kg)}
              />
              <small>kg</small>
            </span>
            {isQuantityFromPassport && (
              <small className="esg-field-source">Resource Passport에서 가져옴</small>
            )}
            {errors.scenario_quantity_kg && (
              <strong className="esg-field-error">{errors.scenario_quantity_kg}</strong>
            )}
          </label>

          <div className="esg-pathway-comparison">
            <label className="esg-field esg-pathway-card">
              <span><b className="esg-field-index">2</b> 현재 처리 방식 <em>필수</em></span>
              <select
                className={errors.baseline_pathway ? 'is-error' : ''}
                value={baselineOption}
                onChange={(event) => {
                  const nextOption = event.target.value
                  setBaselineOption(nextOption)
                  updateValue(
                    'baseline_pathway',
                    nextOption === '기타' ? '' : nextOption,
                  )
                }}
                aria-invalid={Boolean(errors.baseline_pathway)}
              >
                {BASELINE_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
                <option value="기타">기타</option>
              </select>
              {baselineOption === '기타' && (
                <input
                  className={errors.baseline_pathway ? 'is-error' : ''}
                  type="text"
                  placeholder="현재 처리 방식을 입력해주세요"
                  value={values.baseline_pathway}
                  onChange={(event) =>
                    updateValue('baseline_pathway', event.target.value)
                  }
                  aria-invalid={Boolean(errors.baseline_pathway)}
                />
              )}
              <small className="esg-field-source esg-field-source--demo">
                비교 기준 · 사용자 설정
              </small>
              {errors.baseline_pathway && (
                <strong className="esg-field-error">{errors.baseline_pathway}</strong>
              )}
            </label>

            <div className="esg-comparison-arrow" aria-hidden="true">
              <span>비교</span>
              <ArrowRight size={16} strokeWidth={1.8} />
            </div>

            <div className="esg-field esg-pathway-card">
              <span>
                <b className="esg-field-index">3</b>{' '}
                {canUseSelectedCandidate ? '대안 활용 방식' : '가정할 대안 활용 방식'}
                <em>필수</em>
              </span>
              {canUseSelectedCandidate && selectedCandidate ? (
                <div className="esg-selected-alternative">
                  <strong>{selectedCandidate.company_name}</strong>
                  <p>{alternativeDisplayLabel}</p>
                  <small>
                    {decisionStatus === 'APPROVED'
                      ? '최종 선택 후보에서 가져옴'
                      : '추가 확인 중인 후보 기준 · 확정 전 비교'}
                  </small>
                </div>
              ) : (
                <>
                  <input
                    className={errors.alternative_pathway ? 'is-error' : ''}
                    type="text"
                    placeholder="예: 세라믹 원료 파일럿 활용"
                    value={values.alternative_pathway}
                    onChange={(event) =>
                      updateValue('alternative_pathway', event.target.value)
                    }
                    aria-invalid={Boolean(errors.alternative_pathway)}
                  />
                  <small className="esg-field-source">
                    {decisionStatus === 'REJECTED'
                      ? '후보 제외 결정 · 대안 활용 방식을 직접 입력해주세요.'
                      : '현재 선택된 활용 후보 없음 · 직접 입력'}
                  </small>
                </>
              )}
              {errors.alternative_pathway && (
                <strong className="esg-field-error">{errors.alternative_pathway}</strong>
              )}
            </div>
          </div>
        </div>

        <details
          className="esg-detail-fields"
          open={isDetailsOpen}
          onToggle={(event) => setIsDetailsOpen(event.currentTarget.open)}
        >
          <summary className="esg-detail-fields__heading">
            <span>
              <strong>상세 ESG 계수 입력 (선택)</strong>
              <small>계수를 모르면 비워두고 계산해도 됩니다.</small>
            </span>
            <ChevronDown size={16} strokeWidth={1.8} aria-hidden="true" />
          </summary>
          <div className="esg-detail-fields__content">
            <p className="esg-detail-fields__notice">
              <strong>어떤 값을 써야 할지 모른다면 비워두세요.</strong> 자원량은
              계산되며, 에너지·탄소 결과는 ‘계수 미입력’으로 표시됩니다.
            </p>
            <div className="esg-factor-entry-guide">
              <div>
                <strong>현재 처리 방식</strong>
                <p>현재 폐기·소각·외부 처리 등에 필요한 자원 1kg당 값을 입력합니다.</p>
              </div>
              <ArrowRight size={15} strokeWidth={1.8} aria-hidden="true" />
              <div>
                <strong>대안 활용 방식</strong>
                <p>선택한 활용 후보로 처리할 때 필요한 자원 1kg당 값을 입력합니다.</p>
              </div>
            </div>
            <div className="esg-factor-groups">
            <fieldset className="esg-factor-group">
              <legend>에너지 계수 <span>선택사항 · kWh/kg</span></legend>
              <p className="esg-factor-help">자원 1kg을 처리할 때 사용하는 에너지량</p>
              <div>
                <label className="esg-field">
                  <span>현재 처리 방식</span>
                  <input
                    className={errors.baseline_energy_factor_kwh_per_kg ? 'is-error' : ''}
                    type="number"
                    step="any"
                    inputMode="decimal"
                    placeholder="자료의 kWh/kg 값"
                    value={values.baseline_energy_factor_kwh_per_kg}
                    onChange={(event) =>
                      updateValue(
                        'baseline_energy_factor_kwh_per_kg',
                        event.target.value,
                      )
                    }
                    aria-invalid={Boolean(errors.baseline_energy_factor_kwh_per_kg)}
                  />
                  {errors.baseline_energy_factor_kwh_per_kg && (
                    <strong className="esg-field-error">
                      {errors.baseline_energy_factor_kwh_per_kg}
                    </strong>
                  )}
                </label>
                <label className="esg-field">
                  <span>대안 활용 방식</span>
                  <input
                    className={errors.alternative_energy_factor_kwh_per_kg ? 'is-error' : ''}
                    type="number"
                    step="any"
                    inputMode="decimal"
                    placeholder="자료의 kWh/kg 값"
                    value={values.alternative_energy_factor_kwh_per_kg}
                    onChange={(event) =>
                      updateValue(
                        'alternative_energy_factor_kwh_per_kg',
                        event.target.value,
                      )
                    }
                    aria-invalid={Boolean(errors.alternative_energy_factor_kwh_per_kg)}
                  />
                  {errors.alternative_energy_factor_kwh_per_kg && (
                    <strong className="esg-field-error">
                      {errors.alternative_energy_factor_kwh_per_kg}
                    </strong>
                  )}
                </label>
              </div>
            </fieldset>

            <fieldset className="esg-factor-group">
              <legend>탄소 계수 <span>선택사항 · kgCO₂e/kg</span></legend>
              <p className="esg-factor-help">자원 1kg 처리에 대응하는 탄소배출량</p>
              <div>
                <label className="esg-field">
                  <span>현재 처리 방식</span>
                  <input
                    className={errors.baseline_carbon_factor_kgco2e_per_kg ? 'is-error' : ''}
                    type="number"
                    step="any"
                    inputMode="decimal"
                    placeholder="자료의 kgCO₂e/kg 값"
                    value={values.baseline_carbon_factor_kgco2e_per_kg}
                    onChange={(event) =>
                      updateValue(
                        'baseline_carbon_factor_kgco2e_per_kg',
                        event.target.value,
                      )
                    }
                    aria-invalid={Boolean(errors.baseline_carbon_factor_kgco2e_per_kg)}
                  />
                  {errors.baseline_carbon_factor_kgco2e_per_kg && (
                    <strong className="esg-field-error">
                      {errors.baseline_carbon_factor_kgco2e_per_kg}
                    </strong>
                  )}
                </label>
                <label className="esg-field">
                  <span>대안 활용 방식</span>
                  <input
                    className={errors.alternative_carbon_factor_kgco2e_per_kg ? 'is-error' : ''}
                    type="number"
                    step="any"
                    inputMode="decimal"
                    placeholder="자료의 kgCO₂e/kg 값"
                    value={values.alternative_carbon_factor_kgco2e_per_kg}
                    onChange={(event) =>
                      updateValue(
                        'alternative_carbon_factor_kgco2e_per_kg',
                        event.target.value,
                      )
                    }
                    aria-invalid={Boolean(errors.alternative_carbon_factor_kgco2e_per_kg)}
                  />
                  {errors.alternative_carbon_factor_kgco2e_per_kg && (
                    <strong className="esg-field-error">
                      {errors.alternative_carbon_factor_kgco2e_per_kg}
                    </strong>
                  )}
                </label>
              </div>
            </fieldset>
            </div>

            <p className="esg-factor-formula">
              <strong>계산 방식</strong>
              자원량 × (현재 처리 방식 계수 − 대안 활용 방식 계수)
              <span>에너지 또는 탄소의 두 값을 모두 입력한 경우에만 차이를 계산합니다.</span>
            </p>

            <label className="esg-field esg-factor-source">
              <span>계수 출처 <em>{hasAnyFactorInput ? '필수' : '선택사항'}</em></span>
              <input
                className={errors.factor_source ? 'is-error' : ''}
                type="text"
                placeholder="예: 사내 공정자료 / LCA / EPD 자료명"
                value={values.factor_source}
                onChange={(event) => updateValue('factor_source', event.target.value)}
                aria-invalid={Boolean(errors.factor_source)}
              />
              {errors.factor_source && (
                <strong className="esg-field-error">{errors.factor_source}</strong>
              )}
              <small>입력한 에너지·탄소 계수의 근거 자료를 기록합니다.</small>
            </label>
          </div>
        </details>

        <ApiErrorMessage error={apiError} />
        <button
          className="primary-button esg-calculate-button"
          type="submit"
          disabled={isCalculating}
        >
          <Calculator size={17} strokeWidth={1.9} aria-hidden="true" />
          {isCalculating ? '시나리오를 저장하고 있습니다...' : '시나리오 계산 및 저장'}
        </button>
      </form>

      {esgScenario && (
        <div className="esg-results" aria-live="polite">
          <div className="esg-results__status">
            <span className="receipt-badge receipt-badge--scenario">SCENARIO</span>
            <strong>ESG 시나리오 계산 완료</strong>
          </div>
          <div className="esg-pathway-flow" aria-label="ESG 시나리오 비교 경로">
            <span>{esgScenario.inputs.baseline_pathway}</span>
            <ArrowRight size={15} strokeWidth={1.8} aria-hidden="true" />
            <span>{alternativeDisplayLabel ?? esgScenario.inputs.alternative_pathway}</span>
            <strong>예상 차이</strong>
          </div>
          <dl className="esg-result-summary">
            <div>
              <dt>시나리오 적용 자원량</dt>
              <dd>{formatNumber(esgScenario.results.diverted_quantity_kg)} kg</dd>
            </div>
            <div>
              <dt>예상 에너지 차이</dt>
              <dd>{formatDifference(esgScenario.results.energy_difference_kwh, 'kWh')}</dd>
            </div>
            <div>
              <dt>예상 탄소 차이</dt>
              <dd>{formatDifference(esgScenario.results.carbon_difference_kgco2e, 'kgCO₂e')}</dd>
            </div>
          </dl>
          <div className="esg-result-meta">
            <span>계산식 버전 <strong>{esgScenario.formula_version}</strong></span>
            <span>계수 출처 <strong>{esgScenario.factor_source ?? '미입력'}</strong></span>
          </div>
        </div>
      )}

      <p className="esg-scenario-notice">
        사용자 입력값 기반 가정 계산이며 실제 측정값이나 AI 예측값이 아닙니다.
      </p>
    </div>
  )
}
