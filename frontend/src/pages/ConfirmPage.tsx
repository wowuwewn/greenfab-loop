import { useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  RefreshCw,
  RotateCcw,
  UserCheck,
  X,
} from 'lucide-react'
import { WorkflowStepper } from '../components/WorkflowStepper'
import { ApiErrorMessage } from '../components/ApiErrorMessage'
import { toApiError, type ApiError } from '../api/client'
import {
  DETECT_ANALYSIS,
  WORKFLOW_STEPS,
} from '../data/detectData'
import type {
  DetectCase,
  ResourceConfirmation,
  ResourceConfirmationStatus,
} from '../types/loop'
import '../confirm.css'

type ConfirmedStatus = Exclude<ResourceConfirmationStatus, 'PENDING'>

interface ConfirmPageProps {
  caseData: DetectCase
  resourceConfirmation: ResourceConfirmation
  onSelect: (status: ConfirmedStatus) => Promise<void>
  onBackToDetect: () => void
  onGoToPassport: () => void
}

const formatNumber = new Intl.NumberFormat('ko-KR')

export function ConfirmPage({
  caseData,
  resourceConfirmation,
  onSelect,
  onBackToDetect,
  onGoToPassport,
}: ConfirmPageProps) {
  const { status } = resourceConfirmation
  const [isChoosing, setIsChoosing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [apiError, setApiError] = useState<ApiError | null>(null)

  const resetSelection = () => {
    setApiError(null)
    setIsChoosing(true)
  }

  const selectStatus = async (nextStatus: ConfirmedStatus) => {
    setIsSaving(true)
    setApiError(null)

    try {
      await onSelect(nextStatus)
      setIsChoosing(false)
    } catch (error) {
      setApiError(toApiError(error))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="app-shell confirm-page">
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
            onClick={onBackToDetect}
          >
            <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
            위험 선별로 돌아가기
          </button>
        </div>
      </header>

      <main className="page-container confirm-main" id="top">
        <WorkflowStepper steps={WORKFLOW_STEPS} activeStep={1} />

        <section className="hero-copy confirm-hero" aria-labelledby="confirm-title">
          <div className="hero-copy__main">
            <span className="eyebrow">02 · 현장 확인</span>
            <h1 id="confirm-title">실제 자원 발생을 확인합니다</h1>
            <p>
              모델은 우선 확인할 생산 건만 선별합니다.
              <br />
              실제 자원 발생 여부는 현장 담당자가 확인합니다.
            </p>
          </div>
        </section>

        <section className="confirm-case" aria-labelledby="confirm-case-title">
          <div className="confirm-case__identity">
            <span>확인 대상</span>
            <h2 id="confirm-case-title">{caseData.case_id}</h2>
          </div>
          <dl className="confirm-case__details">
            <div>
              <dt>검토 우선순위</dt>
              <dd>
                {caseData.risk_rank ?? '-'}위 /{' '}
                {formatNumber.format(DETECT_ANALYSIS.total_cases)}건
              </dd>
            </div>
            <div>
              <dt>데이터 출처</dt>
              <dd>
                <span
                  className={`source-badge source-badge--${caseData.source_type.toLowerCase()}`}
                >
                  {caseData.source_type}
                </span>
                UCI SECOM + 모델 결과
              </dd>
            </div>
          </dl>
        </section>

        <section className="source-transition" aria-label="모델 분석 결과에서 현장 확인 입력으로 전환">
          <div className="source-transition__side">
            <div className="source-transition__heading">
              <span
                className={`source-badge source-badge--${caseData.source_type.toLowerCase()}`}
              >
                {caseData.source_type}
              </span>
              <strong>모델 분석 결과</strong>
            </div>
            <div className="source-transition__content">
              <p>{caseData.case_id}</p>
              <small>검토 우선순위 {caseData.risk_rank ?? '-'}위</small>
            </div>
          </div>

          <ArrowRight className="source-transition__arrow" size={18} aria-hidden="true" />

          <div className="source-transition__gate">
            <span className="source-transition__gate-icon" aria-hidden="true">
              <UserCheck size={20} strokeWidth={1.8} />
            </span>
            <div className="source-transition__gate-copy">
              <strong>현장 담당자 확인</strong>
              <small>여기부터 사람이 확인</small>
            </div>
          </div>

          <ArrowRight className="source-transition__arrow" size={18} aria-hidden="true" />

          <div className="source-transition__side">
            <div className="source-transition__heading">
              <span
                className={`source-badge source-badge--${resourceConfirmation.source_type.toLowerCase()}`}
              >
                {resourceConfirmation.source_type}
              </span>
              <strong>현장 확인 시나리오</strong>
            </div>
            <div className="source-transition__content">
              <p>실제 자원 발생 여부</p>
              <small>SECOM에 없는 정보를 이번 MVP에서 데모 입력</small>
            </div>
          </div>
        </section>

        <section className="human-gate" aria-labelledby="human-gate-title">
          <div className="human-gate__heading">
            <div>
              <span className="human-gate__label">현장 확인</span>
              <h2 id="human-gate-title">현장에서 실제 자원이 발생했나요?</h2>
              <p>모델 예측이 아니라 현장 확인 결과를 입력합니다.</p>
            </div>
            <span className={`confirmation-status confirmation-status--${status.toLowerCase()}`}>
              {status === 'PENDING' && '현장 확인 대기'}
              {status === 'CONFIRMED' && '확인 완료'}
              {status === 'NOT_CONFIRMED' && '미발생 확인'}
            </span>
          </div>

          {(status === 'PENDING' || isChoosing) && (
            <div className="confirmation-options">
              <button
                className="confirmation-option confirmation-option--neutral"
                type="button"
                onClick={() => selectStatus('CONFIRMED')}
                disabled={isSaving}
              >
                <span className="confirmation-option__icon" aria-hidden="true">
                  <Check size={18} strokeWidth={2.2} />
                </span>
                <span>
                  <strong>발생 확인</strong>
                  <small>확인된 자원의 정보를 다음 단계에서 정리합니다.</small>
                </span>
              </button>
              <button
                className="confirmation-option confirmation-option--neutral"
                type="button"
                onClick={() => selectStatus('NOT_CONFIRMED')}
                disabled={isSaving}
              >
                <span className="confirmation-option__icon" aria-hidden="true">
                  <X size={18} strokeWidth={2} />
                </span>
                <span>
                  <strong>발생하지 않음</strong>
                  <small>이 Case의 자원 순환 검토를 종료합니다.</small>
                </span>
              </button>
            </div>
          )}

          <ApiErrorMessage error={apiError} />

          {status === 'CONFIRMED' && !isChoosing && (
            <div className="confirmation-result confirmation-result--confirmed">
              <CheckCircle2 size={24} strokeWidth={1.9} aria-hidden="true" />
              <div className="confirmation-result__copy">
                <strong>실제 자원 발생 확인 완료</strong>
                <p>확인된 자원의 종류, 수량, 상태 등 정보를 정리합니다.</p>
              </div>
              <div className="confirmation-result__actions">
                <button
                  className="primary-button confirmation-result__primary"
                  type="button"
                  onClick={onGoToPassport}
                >
                  자원 정보 작성으로 이동
                  <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                </button>
                <button className="confirm-reset-button" type="button" onClick={resetSelection}>
                  <RotateCcw size={14} strokeWidth={1.9} aria-hidden="true" />
                  다시 선택
                </button>
              </div>
            </div>
          )}

          {status === 'NOT_CONFIRMED' && !isChoosing && (
            <div className="confirmation-result confirmation-result--empty">
              <X size={24} strokeWidth={1.9} aria-hidden="true" />
              <div className="confirmation-result__copy">
                <strong>이번 Case에서는 확인된 자원이 없습니다.</strong>
                <p>자원이 확인되지 않아 이 Case의 자원 순환 검토를 종료합니다.</p>
              </div>
              <div className="confirmation-result__actions">
                <button
                  className="primary-button confirmation-result__primary"
                  type="button"
                  onClick={onBackToDetect}
                >
                  위험 선별로 돌아가기
                  <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                </button>
                <button className="confirm-reset-button" type="button" onClick={resetSelection}>
                  <RotateCcw size={14} strokeWidth={1.9} aria-hidden="true" />
                  다시 선택
                </button>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
