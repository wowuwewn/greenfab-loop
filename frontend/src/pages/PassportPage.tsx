import { useState, type FormEvent } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileText,
  Pencil,
  RefreshCw,
} from 'lucide-react'
import { WorkflowStepper } from '../components/WorkflowStepper'
import { PRIORITY_CASE, WORKFLOW_STEPS } from '../data/detectData'
import type { ResourceConfirmation, ResourcePassport } from '../types/loop'
import '../passport.css'

interface PassportPageProps {
  resourceConfirmation: ResourceConfirmation
  resourcePassport: ResourcePassport | null
  onSave: (resourcePassport: ResourcePassport) => void
  onBackToConfirm: () => void
}

interface PassportFormValues {
  description: string
  quantity: string
  unit: string
  condition: string
  location: string
  composition: string
}

interface PassportFormErrors {
  description?: string
  quantity?: string
}

const PASSPORT_ID = 'PASSPORT-DEMO-0116'

const toFormValues = (
  resourcePassport: ResourcePassport | null,
): PassportFormValues => ({
  description: resourcePassport?.description ?? '',
  quantity:
    resourcePassport?.quantity === null ||
    resourcePassport?.quantity === undefined
      ? ''
      : String(resourcePassport.quantity),
  unit: resourcePassport?.unit ?? '',
  condition: resourcePassport?.condition ?? '',
  location: resourcePassport?.location ?? '',
  composition: resourcePassport?.composition ?? '',
})

const optionalText = (value: string) => value.trim() || null

export function PassportPage({
  resourceConfirmation,
  resourcePassport,
  onSave,
  onBackToConfirm,
}: PassportPageProps) {
  const [formValues, setFormValues] = useState<PassportFormValues>(() =>
    toFormValues(resourcePassport),
  )
  const [errors, setErrors] = useState<PassportFormErrors>({})
  const [hasSubmitted, setHasSubmitted] = useState(false)
  const [isEditing, setIsEditing] = useState(resourcePassport === null)
  const [showMatchNotice, setShowMatchNotice] = useState(false)

  const updateField = (field: keyof PassportFormValues, value: string) => {
    setFormValues((current) => ({ ...current, [field]: value }))
    if (field === 'description' || field === 'quantity') {
      setErrors((current) => ({ ...current, [field]: undefined }))
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setHasSubmitted(true)

    const nextErrors: PassportFormErrors = {}
    const description = formValues.description.trim()
    const quantity =
      formValues.quantity.trim() === '' ? null : Number(formValues.quantity)

    if (!description) {
      nextErrors.description = '후보 탐색을 위해 자원 설명을 입력해주세요.'
    }

    if (
      quantity !== null &&
      (!Number.isFinite(quantity) || quantity < 0)
    ) {
      nextErrors.quantity = '수량은 0 이상의 숫자로 입력해주세요.'
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }

    onSave({
      passport_id: PASSPORT_ID,
      description,
      quantity,
      unit: optionalText(formValues.unit),
      condition: optionalText(formValues.condition),
      location: optionalText(formValues.location),
      composition: optionalText(formValues.composition),
      source_type: 'DEMO',
    })
    setErrors({})
    setHasSubmitted(false)
    setShowMatchNotice(false)
    setIsEditing(false)
  }

  const startEditing = () => {
    setFormValues(toFormValues(resourcePassport))
    setErrors({})
    setHasSubmitted(false)
    setShowMatchNotice(false)
    setIsEditing(true)
  }

  const isConfirmed = resourceConfirmation.status === 'CONFIRMED'

  return (
    <div className="app-shell passport-page">
      <header className="topbar">
        <div className="page-container topbar__inner">
          <a className="brand" href="#top" aria-label="GreenFab Loop 홈">
            <span className="brand__mark" aria-hidden="true">
              <RefreshCw size={17} strokeWidth={2} />
            </span>
            <span>GreenFab Loop</span>
          </a>
          <button
            className="overview-back-button"
            type="button"
            onClick={onBackToConfirm}
          >
            <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
            현장 확인으로 돌아가기
          </button>
        </div>
      </header>

      <main className="page-container passport-main" id="top">
        <WorkflowStepper steps={WORKFLOW_STEPS} activeStep={2} />

        <section className="hero-copy passport-hero" aria-labelledby="passport-title">
          <div className="hero-copy__main">
            <span className="eyebrow">03 · 자원 정보</span>
            <h1 id="passport-title">확인된 자원 정보를 정리합니다</h1>
            <p>
              다음 활용 후보를 찾기 위해 현장에서 확인한 자원의 정보를 입력합니다.
            </p>
            <small>
              SECOM에는 자원 상세 정보가 없어 이번 MVP에서는 DEMO 입력으로 구분합니다.
            </small>
          </div>
        </section>

        <section className="passport-context" aria-label="자원 정보 연결 맥락">
          <div>
            <span>연결된 생산 건</span>
            <strong>{PRIORITY_CASE.case_id}</strong>
          </div>
          <div>
            <span>현장 확인</span>
            <strong className="passport-context__confirmed">
              <CheckCircle2 size={15} strokeWidth={2} aria-hidden="true" />
              {resourceConfirmation.status === 'CONFIRMED'
                ? '발생 확인 완료'
                : resourceConfirmation.status}
            </strong>
          </div>
          <div>
            <span>데이터 구분</span>
            <p>
              <span className="source-badge source-badge--real">REAL</span>
              생산 Case
              <span className="passport-context__divider" aria-hidden="true" />
              <span className="source-badge source-badge--demo">DEMO</span>
              자원 정보
            </p>
          </div>
        </section>

        {!isConfirmed ? (
          <section className="passport-blocked" aria-labelledby="passport-blocked-title">
            <span className="passport-blocked__icon" aria-hidden="true">
              <FileText size={23} strokeWidth={1.8} />
            </span>
            <div>
              <h2 id="passport-blocked-title">먼저 실제 자원 발생 여부를 확인해야 합니다.</h2>
              <p>현장 확인이 완료된 자원만 정보를 작성할 수 있습니다.</p>
            </div>
            <button className="primary-button passport-blocked__button" type="button" onClick={onBackToConfirm}>
              현장 확인으로 돌아가기
              <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
            </button>
          </section>
        ) : (
          <section className="passport-surface" aria-labelledby="passport-form-title">
            <div className="passport-surface__heading">
              <div>
                <h2 id="passport-form-title">자원 상세 정보</h2>
                <p>확인된 정보만 입력하고 모르는 항목은 비워둘 수 있습니다.</p>
              </div>
              <div className="passport-demo-label">
                <span className="source-badge source-badge--demo">DEMO</span>
                <div>
                  <strong>자원 상세 정보</strong>
                  <small>SECOM에 없는 현장 Resource 정보를 이번 MVP에서 데모 입력</small>
                </div>
              </div>
            </div>

            {isEditing ? (
              <form className="passport-form" onSubmit={handleSubmit} noValidate>
                <label className="passport-field passport-field--full">
                  <span>자원 설명 <em>필수</em></span>
                  <textarea
                    value={formValues.description}
                    onChange={(event) => updateField('description', event.target.value)}
                    aria-invalid={hasSubmitted && Boolean(errors.description)}
                    aria-describedby="description-helper description-error"
                    rows={3}
                  />
                  <small id="description-helper">AI 후보 탐색에 사용할 자원 설명입니다.</small>
                  {hasSubmitted && errors.description && (
                    <strong className="passport-field__error" id="description-error">
                      {errors.description}
                    </strong>
                  )}
                </label>

                <label className="passport-field">
                  <span>수량 <em>선택사항</em></span>
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={formValues.quantity}
                    onChange={(event) => updateField('quantity', event.target.value)}
                    aria-invalid={hasSubmitted && Boolean(errors.quantity)}
                    aria-describedby="quantity-error"
                  />
                  {hasSubmitted && errors.quantity && (
                    <strong className="passport-field__error" id="quantity-error">
                      {errors.quantity}
                    </strong>
                  )}
                </label>

                <label className="passport-field">
                  <span>단위 <em>선택사항</em></span>
                  <input
                    type="text"
                    placeholder="예: kg"
                    value={formValues.unit}
                    onChange={(event) => updateField('unit', event.target.value)}
                  />
                </label>

                <label className="passport-field">
                  <span>현재 상태 <em>선택사항</em></span>
                  <input
                    type="text"
                    placeholder="현장에서 확인한 상태를 입력하세요"
                    value={formValues.condition}
                    onChange={(event) => updateField('condition', event.target.value)}
                  />
                </label>

                <label className="passport-field">
                  <span>보관 / 발생 위치 <em>선택사항</em></span>
                  <input
                    type="text"
                    value={formValues.location}
                    onChange={(event) => updateField('location', event.target.value)}
                  />
                </label>

                <label className="passport-field passport-field--full">
                  <span>재질·구성 정보 <em>선택사항</em></span>
                  <textarea
                    value={formValues.composition}
                    onChange={(event) => updateField('composition', event.target.value)}
                    rows={2}
                  />
                  <small>확인되지 않은 정보는 비워둘 수 있습니다.</small>
                </label>

                <div className="passport-form__actions passport-field--full">
                  <button className="primary-button passport-save-button" type="submit">
                    자원 정보 저장
                    <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                  </button>
                </div>
              </form>
            ) : (
              resourcePassport && (
                <div className="passport-complete">
                  <div className="passport-complete__status">
                    <CheckCircle2 size={22} strokeWidth={1.9} aria-hidden="true" />
                    <div>
                      <strong>자원 정보 저장 완료</strong>
                      <span>{resourcePassport.passport_id}</span>
                    </div>
                  </div>

                  <dl className="passport-summary">
                    <div className="passport-summary__full">
                      <dt>자원 설명</dt>
                      <dd>{resourcePassport.description}</dd>
                    </div>
                    <div>
                      <dt>수량</dt>
                      <dd>{resourcePassport.quantity ?? '미입력'}</dd>
                    </div>
                    <div>
                      <dt>단위</dt>
                      <dd>{resourcePassport.unit ?? '미입력'}</dd>
                    </div>
                    <div>
                      <dt>현재 상태</dt>
                      <dd>{resourcePassport.condition ?? '미입력'}</dd>
                    </div>
                    <div>
                      <dt>위치</dt>
                      <dd>{resourcePassport.location ?? '미입력'}</dd>
                    </div>
                    <div className="passport-summary__full">
                      <dt>재질·구성</dt>
                      <dd>{resourcePassport.composition ?? '미입력'}</dd>
                    </div>
                  </dl>

                  <div className="passport-complete__actions">
                    <button
                      className="primary-button passport-match-button"
                      type="button"
                      onClick={() => setShowMatchNotice(true)}
                    >
                      후보 탐색으로 이동
                      <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                    </button>
                    <button className="secondary-button passport-edit-button" type="button" onClick={startEditing}>
                      <Pencil size={14} strokeWidth={1.9} aria-hidden="true" />
                      입력 내용 수정
                    </button>
                  </div>

                  <div
                    className={`inline-notice passport-inline-notice${showMatchNotice ? ' is-visible' : ''}`}
                    aria-live="polite"
                  >
                    <CheckCircle2 size={16} strokeWidth={2} aria-hidden="true" />
                    <span>후보 탐색 화면은 다음 단계에서 연결됩니다.</span>
                  </div>
                </div>
              )
            )}
          </section>
        )}
      </main>
    </div>
  )
}
