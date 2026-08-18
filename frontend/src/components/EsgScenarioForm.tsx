import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, Calculator } from 'lucide-react'
import type { EsgScenario } from '../types/loop'

interface EsgScenarioFormProps {
  esgScenario: EsgScenario | null
  onCalculate: (scenario: EsgScenario) => void
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

const initialValues = (scenario: EsgScenario | null): EsgFormValues => ({
  scenario_quantity_kg: scenario
    ? String(scenario.inputs.scenario_quantity_kg)
    : '',
  baseline_pathway: scenario?.inputs.baseline_pathway ?? '',
  alternative_pathway: scenario?.inputs.alternative_pathway ?? '',
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
  onCalculate,
}: EsgScenarioFormProps) {
  const [values, setValues] = useState<EsgFormValues>(() =>
    initialValues(esgScenario),
  )
  const [errors, setErrors] = useState<EsgFormErrors>({})

  const updateValue = (field: keyof EsgFormValues, value: string) => {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

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

    return parsedValue
  }

  const calculateScenario = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const nextErrors: EsgFormErrors = {}
    const quantity = Number(values.scenario_quantity_kg)
    const baselinePathway = values.baseline_pathway.trim()
    const alternativePathway = values.alternative_pathway.trim()

    if (!values.scenario_quantity_kg.trim()) {
      nextErrors.scenario_quantity_kg = '시나리오 자원량을 입력해주세요.'
    } else if (!Number.isFinite(quantity) || quantity <= 0) {
      nextErrors.scenario_quantity_kg = '0보다 큰 숫자를 입력해주세요.'
    }

    if (!baselinePathway) {
      nextErrors.baseline_pathway = '기존 처리 경로를 입력해주세요.'
    }

    if (!alternativePathway) {
      nextErrors.alternative_pathway = '순환 경로를 입력해주세요.'
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
    const hasAnyFactorInput = [
      values.baseline_energy_factor_kwh_per_kg,
      values.alternative_energy_factor_kwh_per_kg,
      values.baseline_carbon_factor_kgco2e_per_kg,
      values.alternative_carbon_factor_kgco2e_per_kg,
    ].some((value) => value.trim() !== '')

    if (hasAnyFactorInput && !values.factor_source.trim()) {
      nextErrors.factor_source = '입력한 계수의 출처를 함께 기록해주세요.'
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

    onCalculate({
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
  }

  return (
    <div className="esg-scenario-content">
      <form className="esg-form" onSubmit={calculateScenario} noValidate>
        <div className="esg-form__primary-fields">
          <label className="esg-field">
            <span>시나리오 자원량 <em>필수</em></span>
            <span className={`esg-input-with-unit${errors.scenario_quantity_kg ? ' is-error' : ''}`}>
              <input
                type="number"
                min="0"
                step="any"
                inputMode="decimal"
                value={values.scenario_quantity_kg}
                onChange={(event) =>
                  updateValue('scenario_quantity_kg', event.target.value)
                }
                aria-invalid={Boolean(errors.scenario_quantity_kg)}
              />
              <small>kg</small>
            </span>
            {errors.scenario_quantity_kg && (
              <strong className="esg-field-error">{errors.scenario_quantity_kg}</strong>
            )}
          </label>

          <label className="esg-field">
            <span>기존 처리 경로 <em>필수</em></span>
            <input
              className={errors.baseline_pathway ? 'is-error' : ''}
              type="text"
              placeholder="예: 기존 폐기 처리"
              value={values.baseline_pathway}
              onChange={(event) =>
                updateValue('baseline_pathway', event.target.value)
              }
              aria-invalid={Boolean(errors.baseline_pathway)}
            />
            {errors.baseline_pathway && (
              <strong className="esg-field-error">{errors.baseline_pathway}</strong>
            )}
          </label>

          <label className="esg-field">
            <span>순환 경로 <em>필수</em></span>
            <input
              className={errors.alternative_pathway ? 'is-error' : ''}
              type="text"
              placeholder="예: 재사용 또는 재활용"
              value={values.alternative_pathway}
              onChange={(event) =>
                updateValue('alternative_pathway', event.target.value)
              }
              aria-invalid={Boolean(errors.alternative_pathway)}
            />
            {errors.alternative_pathway && (
              <strong className="esg-field-error">{errors.alternative_pathway}</strong>
            )}
          </label>
        </div>

        <div className="esg-factor-groups">
          <fieldset className="esg-factor-group">
            <legend>에너지 계수 <span>선택사항 · kWh/kg</span></legend>
            <div>
              <label className="esg-field">
                <span>기존 경로</span>
                <input
                  className={errors.baseline_energy_factor_kwh_per_kg ? 'is-error' : ''}
                  type="number"
                  step="any"
                  inputMode="decimal"
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
                <span>순환 경로</span>
                <input
                  className={errors.alternative_energy_factor_kwh_per_kg ? 'is-error' : ''}
                  type="number"
                  step="any"
                  inputMode="decimal"
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
            <div>
              <label className="esg-field">
                <span>기존 경로</span>
                <input
                  className={errors.baseline_carbon_factor_kgco2e_per_kg ? 'is-error' : ''}
                  type="number"
                  step="any"
                  inputMode="decimal"
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
                <span>순환 경로</span>
                <input
                  className={errors.alternative_carbon_factor_kgco2e_per_kg ? 'is-error' : ''}
                  type="number"
                  step="any"
                  inputMode="decimal"
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

        <label className="esg-field esg-factor-source">
          <span>계수 출처 <em>선택사항</em></span>
          <input
            className={errors.factor_source ? 'is-error' : ''}
            type="text"
            value={values.factor_source}
            onChange={(event) => updateValue('factor_source', event.target.value)}
            aria-invalid={Boolean(errors.factor_source)}
          />
          {errors.factor_source && (
            <strong className="esg-field-error">{errors.factor_source}</strong>
          )}
          <small>
            기업 공정자료, LCA/EPD, 검증된 외부 자료 등 사용한 계수의 출처를
            기록합니다.
          </small>
        </label>

        <button className="primary-button esg-calculate-button" type="submit">
          <Calculator size={17} strokeWidth={1.9} aria-hidden="true" />
          시나리오 계산
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
            <span>{esgScenario.inputs.alternative_pathway}</span>
            <strong>예상 차이</strong>
          </div>
          <dl className="esg-result-summary">
            <div>
              <dt>시나리오상 폐기 전환량</dt>
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
        사용자 입력값과 입력된 계수를 기반으로 한 시나리오 계산이며, 실제 측정값이나
        AI 예측값이 아닙니다.
      </p>
    </div>
  )
}
