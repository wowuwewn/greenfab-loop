import { useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  CheckCircle2,
  CircleAlert,
  ListChecks,
  RefreshCw,
  Search,
  UserCheck,
} from 'lucide-react'
import { WorkflowStepper } from '../components/WorkflowStepper'
import { ApiErrorMessage } from '../components/ApiErrorMessage'
import {
  fieldMatches,
  toApiError,
  type ApiError,
  type ApiFieldError,
} from '../api/client'
import { WORKFLOW_STEPS } from '../data/detectData'
import type {
  Decision,
  DecisionDraft,
  DecisionStatus,
  Match,
  MatchCandidate,
} from '../types/loop'
import '../review.css'

interface ReviewPageProps {
  match: Match | null
  decision: Decision | null
  onDecisionChange: (decision: DecisionDraft) => Promise<void>
  onBack: () => void
  onGoToReceipt: () => void
}

interface DecisionErrors {
  status?: string
  candidate?: string
  reason?: string
}

const candidateStatusLabels: Record<MatchCandidate['status'], string> = {
  REVIEW: '검토 가능',
  NEEDS_INFO: '추가 정보 필요',
  RULE_FAIL: '조건 불충족',
}

const decisionLabels: Record<DecisionStatus, string> = {
  APPROVED: '파일럿 검토 승인',
  HOLD: '추가 확인 후 보류',
  REJECTED: '후보 제외',
}

const fieldLabels: Record<string, string> = {
  composition: '재질·구성 정보',
  location: '위치',
  quantity: '수량',
  required_info: '필수정보',
}

const ruleLabels = [
  ['quantity', '수량 조건'],
  ['required_info', '필수정보'],
  ['location', '위치 조건'],
] as const

const ruleValueLabel = (key: (typeof ruleLabels)[number][0], value: boolean | null) => {
  if (value === true) return '✓ 조건 충족'
  if (value === false) {
    return key === 'required_info' ? '! 추가 확인' : '× 조건 불충족'
  }
  return '— 미평가'
}

const ruleValueClass = (value: boolean | null) => {
  if (value === true) return 'is-pass'
  if (value === false) return 'is-fail'
  return 'is-unknown'
}

const formatDecisionTime = (value: string) =>
  new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))

export function ReviewPage({
  match,
  decision,
  onDecisionChange,
  onBack,
  onGoToReceipt,
}: ReviewPageProps) {
  const [selectedDemandId, setSelectedDemandId] = useState<string | null>(
    decision?.selected_demand_id ?? null,
  )
  const [decisionStatus, setDecisionStatus] = useState<DecisionStatus | null>(
    decision?.status ?? null,
  )
  const [reason, setReason] = useState(decision?.reason ?? '')
  const [errors, setErrors] = useState<DecisionErrors>({})
  const [isEditing, setIsEditing] = useState(decision === null)
  const [isSaving, setIsSaving] = useState(false)
  const [apiError, setApiError] = useState<ApiError | null>(null)
  const [unmappedFieldErrors, setUnmappedFieldErrors] = useState<
    ApiFieldError[]
  >([])

  const candidates = match?.candidates ?? []
  const hasCandidates = candidates.length > 0
  const selectedCandidate =
    candidates.find((candidate) => candidate.demand_id === selectedDemandId) ??
    null

  const selectCandidate = (candidate: MatchCandidate) => {
    setSelectedDemandId(candidate.demand_id)
    setErrors((current) => ({ ...current, candidate: undefined }))
  }

  const selectDecisionStatus = (status: DecisionStatus) => {
    setDecisionStatus(status)
    setErrors((current) => ({
      ...current,
      status: undefined,
      candidate: status === 'APPROVED' ? current.candidate : undefined,
    }))
  }

  const saveDecision = async () => {
    if (!hasCandidates) return

    setApiError(null)
    setUnmappedFieldErrors([])

    const nextErrors: DecisionErrors = {}
    const trimmedReason = reason.trim()

    if (!decisionStatus) {
      nextErrors.status = '최종 결정 상태를 선택해주세요.'
    }

    if (decisionStatus === 'APPROVED' && !selectedCandidate) {
      nextErrors.candidate = '승인할 활용 후보를 먼저 선택해주세요.'
    }

    if (
      decisionStatus === 'APPROVED' &&
      selectedCandidate &&
      selectedCandidate.status !== 'REVIEW'
    ) {
      nextErrors.candidate = '검토 가능 상태의 후보만 승인할 수 있습니다.'
    }

    if (!trimmedReason) {
      nextErrors.reason = '결정 사유를 입력해주세요.'
    } else if (trimmedReason.length < 10) {
      nextErrors.reason = '결정 사유는 10자 이상 입력해주세요.'
    }

    if (Object.keys(nextErrors).length > 0 || !decisionStatus) {
      setErrors(nextErrors)
      return
    }

    setIsSaving(true)
    setErrors({})

    try {
      await onDecisionChange({
        status: decisionStatus,
        selected_demand_id: selectedDemandId,
        reason: trimmedReason,
      })
      setErrors({})
      setIsEditing(false)
    } catch (error) {
      const nextApiError = toApiError(error)
      const serverErrors: DecisionErrors = {}
      const unmapped: ApiFieldError[] = []

      nextApiError.fieldErrors.forEach((fieldError) => {
        if (fieldMatches(fieldError.field, 'reason')) {
          serverErrors.reason = fieldError.message
        } else if (fieldMatches(fieldError.field, 'selected_demand_id')) {
          serverErrors.candidate = fieldError.message
        } else if (fieldMatches(fieldError.field, 'status')) {
          serverErrors.status = fieldError.message
        } else {
          unmapped.push(fieldError)
        }
      })

      setErrors((current) => ({ ...current, ...serverErrors }))
      setApiError(nextApiError)
      setUnmappedFieldErrors(unmapped)
    } finally {
      setIsSaving(false)
    }
  }

  const editDecision = () => {
    setSelectedDemandId(decision?.selected_demand_id ?? null)
    setDecisionStatus(decision?.status ?? null)
    setReason(decision?.reason ?? '')
    setErrors({})
    setApiError(null)
    setUnmappedFieldErrors([])
    setIsEditing(true)
  }

  return (
    <div className="app-shell review-page">
      <header className="topbar">
        <div className="page-container topbar__inner">
          <a className="brand" href="#top" aria-label="GreenFab Loop 홈">
            <span className="brand__mark" aria-hidden="true">
              <RefreshCw size={17} strokeWidth={2} />
            </span>
            <span>GreenFab Loop</span>
          </a>
          <button className="overview-back-button" type="button" onClick={onBack}>
            <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
            후보 탐색으로 돌아가기
          </button>
        </div>
      </header>

      <main className="page-container review-main" id="top">
        <WorkflowStepper
          steps={WORKFLOW_STEPS}
          activeStep={4}
          completedStepIndexes={hasCandidates ? [0, 1, 2, 3] : [0, 1, 2]}
        />

        <section className="hero-copy review-hero" aria-labelledby="review-title">
          <div className="hero-copy__main">
            <span className="eyebrow">05 · 최종 검토</span>
            <h1 id="review-title">활용 후보를 검토하고 최종 결정합니다</h1>
            <p>
              AI가 찾은 후보와 규칙 확인 결과를 참고해 담당자가 최종 판단합니다.
            </p>
            <div className="review-principle" aria-label="후보 탐색부터 최종 결정까지의 역할">
              <span><Bot size={14} aria-hidden="true" /><strong>AI</strong> · 후보 탐색</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span><ListChecks size={14} aria-hidden="true" /><strong>RULE</strong> · 조건 확인</span>
              <ArrowRight size={14} aria-hidden="true" />
              <span><UserCheck size={14} aria-hidden="true" /><strong>HUMAN</strong> · 최종 결정</span>
            </div>
          </div>
        </section>

        <div className="review-layout">
          <section className="candidate-surface" aria-labelledby="candidate-title">
            <div className="review-surface-heading">
              <div>
                <span>AI + RULE</span>
                <h2 id="candidate-title">후보 검토</h2>
                <p>의미가 가까운 후보와 명확한 조건 확인 결과를 함께 봅니다.</p>
              </div>
              <span className={`match-state${hasCandidates ? ' is-connected' : ''}`}>
                04 후보 탐색 · {hasCandidates ? '연결 완료' : '연결 대기'}
              </span>
            </div>

            {hasCandidates && (
              <p className="review-selection-guide">
                <CheckCircle2 size={15} strokeWidth={1.9} aria-hidden="true" />
                검토 가능한 후보를 선택한 뒤 최종 결정을 내려주세요.
              </p>
            )}

            {!hasCandidates ? (
              <div className="candidate-empty">
                <span aria-hidden="true"><Search size={25} strokeWidth={1.7} /></span>
                <h3>후보 탐색 결과를 기다리고 있습니다</h3>
                <p>
                  후보 탐색 결과가 연결되면 여기에서 후보와 규칙 확인 결과를 검토할 수 있습니다.
                </p>
              </div>
            ) : (
              <div className="candidate-list">
                {candidates.map((candidate, index) => {
                  const isSelected = selectedDemandId === candidate.demand_id

                  return (
                    <button
                      className={`candidate-row${isSelected ? ' is-selected' : ''}`}
                      type="button"
                      key={candidate.demand_id}
                      onClick={() => selectCandidate(candidate)}
                      aria-pressed={isSelected}
                      disabled={isSaving}
                    >
                      <div className="candidate-row__topline">
                        <span>{index + 1}순위</span>
                        <div className="candidate-row__badges">
                          {isSelected && (
                            <span className="candidate-selected-label">
                              <CheckCircle2 size={12} strokeWidth={2} aria-hidden="true" />
                              선택됨
                            </span>
                          )}
                          <span className={`candidate-status candidate-status--${candidate.status.toLowerCase()}`}>
                            {candidateStatusLabels[candidate.status]}
                          </span>
                        </div>
                      </div>
                      <div className="candidate-row__identity">
                        <div>
                          <strong>{candidate.company_name}</strong>
                          <small>{candidate.demand_id}</small>
                        </div>
                        <span className="similarity-value">
                          {candidate.semantic_similarity === null
                            ? '의미 유사도 계산값 없음'
                            : `의미 유사도 ${candidate.semantic_similarity.toFixed(3)}`}
                        </span>
                      </div>
                      <p>{candidate.demand_description}</p>
                      <dl className="rule-results">
                        {ruleLabels.map(([key, label]) => {
                          const value = candidate.rule_check[key]
                          return (
                            <div key={key}>
                              <dt>{label}</dt>
                              <dd
                                className={`${ruleValueClass(value)}${
                                  key === 'required_info' && value === false
                                    ? ' is-needs-info'
                                    : ''
                                }`}
                              >
                                {ruleValueLabel(key, value)}
                              </dd>
                            </div>
                          )
                        })}
                      </dl>
                      {candidate.rule_check.missing_fields &&
                        candidate.rule_check.missing_fields.length > 0 && (
                          <div className="missing-fields">
                            <strong>추가 확인 필요</strong>
                            <span>
                              누락 정보: {candidate.rule_check.missing_fields
                                .map((field) => fieldLabels[field] ?? field)
                                .join(', ')}
                            </span>
                          </div>
                        )}
                    </button>
                  )
                })}
                <p className="review-rule-help">
                  미평가: 해당 후보에 적용할 조건이 없거나 현재 정보로 평가하지 않은 항목
                </p>
                <p className="similarity-note">
                  의미 유사도는 문장 의미가 얼마나 가까운지를 나타내며, 산업 적합도나 성공 확률을 의미하지 않습니다.
                </p>
              </div>
            )}
          </section>

          <section className="decision-surface" aria-labelledby="decision-title">
            <div className="review-surface-heading decision-surface__heading">
              <div>
                <span>HUMAN · 최종 결정</span>
                <h2 id="decision-title">최종 판단은 담당자가 직접 선택합니다.</h2>
              </div>
            </div>

            {hasCandidates && decision && !isEditing ? (
              <div className="decision-complete">
                <div className="decision-complete__status">
                  <CheckCircle2 size={22} strokeWidth={1.9} aria-hidden="true" />
                  <strong>최종 결정 저장 완료</strong>
                </div>
                <dl>
                  <div><dt>결정</dt><dd>{decisionLabels[decision.status]}</dd></div>
                  <div><dt>선택 후보</dt><dd>{selectedCandidate?.company_name ?? '미선택'}</dd></div>
                  <div><dt>결정 사유</dt><dd>{decision.reason ?? '미입력'}</dd></div>
                  <div><dt>결정자</dt><dd>{decision.decided_by}</dd></div>
                  <div><dt>결정 시각</dt><dd>{formatDecisionTime(decision.decided_at)}</dd></div>
                </dl>
                <div className="decision-complete__actions">
                  <button className="primary-button review-receipt-button" type="button" onClick={onGoToReceipt}>
                    결과 기록으로 이동
                    <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                  </button>
                  <button className="secondary-button review-edit-button" type="button" onClick={editDecision}>
                    결정 수정
                  </button>
                </div>
              </div>
            ) : (
              <div className={`decision-form${hasCandidates ? '' : ' is-disabled'}`}>
                <ApiErrorMessage
                  error={apiError}
                  fieldErrors={unmappedFieldErrors}
                />
                <div className="selected-candidate-summary">
                  <span>선택 후보</span>
                  {selectedCandidate ? (
                    <div>
                      <strong>{selectedCandidate.company_name}</strong>
                      <small>{selectedCandidate.demand_id}</small>
                      {selectedCandidate.semantic_similarity !== null && (
                        <em>의미 유사도 {selectedCandidate.semantic_similarity.toFixed(3)}</em>
                      )}
                    </div>
                  ) : (
                    <p>{hasCandidates ? '후보를 먼저 선택해주세요' : '후보 탐색 결과가 연결된 후 최종 결정을 진행할 수 있습니다.'}</p>
                  )}
                </div>

                <div className="decision-status-field">
                  <span>결정 상태</span>
                  <div>
                    {(['APPROVED', 'HOLD', 'REJECTED'] as const).map((status) => (
                      <button
                        className={`decision-status-button decision-status-button--${status.toLowerCase()}${decisionStatus === status ? ' is-selected' : ''}`}
                        type="button"
                        key={status}
                        onClick={() => selectDecisionStatus(status)}
                        disabled={!hasCandidates || isSaving}
                      >
                        {decisionLabels[status]}
                      </button>
                    ))}
                  </div>
                  {errors.status && <strong className="review-field-error">{errors.status}</strong>}
                  {errors.candidate && <strong className="review-field-error">{errors.candidate}</strong>}
                </div>

                <div className="decision-reason-field">
                  <div className="decision-reason-heading">
                    <label htmlFor="decision-reason">
                      결정 사유 <em>필수 · 10자 이상</em>
                    </label>
                    <button
                      className="decision-demo-fill-button"
                      type="button"
                      onClick={() => {
                        const demoReason =
                          decisionStatus === 'APPROVED'
                            ? 'DEMO: 의미 유사도와 Rule 확인 결과를 참고해 담당자가 소량 파일럿 검토를 승인합니다. 실제 활용 적합성은 별도 확인합니다.'
                            : decisionStatus === 'HOLD'
                              ? 'DEMO: 의미 유사도와 Rule 확인 결과를 참고했으나 필수정보 확인이 필요해 담당자가 추가 검토 전까지 보류합니다.'
                              : decisionStatus === 'REJECTED'
                                ? 'DEMO: 의미 유사도와 명시된 Rule 조건을 검토한 결과 담당자가 현재 후보를 제외합니다.'
                                : 'DEMO: 의미 유사도와 Rule 확인 결과를 참고하고, 담당자가 실제 활용 조건을 추가 검토합니다.'
                        setReason(demoReason)
                        setErrors((current) => ({ ...current, reason: undefined }))
                      }}
                      disabled={!hasCandidates || isSaving}
                    >
                      데모 사유 자동입력
                    </button>
                  </div>
                  <textarea
                    id="decision-reason"
                    rows={4}
                    maxLength={2000}
                    placeholder="예: 성분 분석 완료 후 소량 파일럿 검토를 진행합니다."
                    value={reason}
                    onChange={(event) => {
                      setReason(event.target.value)
                      setErrors((current) => ({ ...current, reason: undefined }))
                    }}
                    disabled={!hasCandidates || isSaving}
                    aria-invalid={Boolean(errors.reason)}
                    aria-describedby="decision-reason-count decision-reason-error"
                  />
                  <small className="decision-reason-count" id="decision-reason-count">
                    {reason.trim().length} / 최소 10자
                  </small>
                  {errors.reason && (
                    <strong className="review-field-error" id="decision-reason-error">
                      {errors.reason}
                    </strong>
                  )}
                </div>

                <button
                  className="primary-button review-save-button"
                  type="button"
                  onClick={saveDecision}
                  disabled={!hasCandidates || isSaving}
                >
                  {isSaving ? '결정을 저장하고 있습니다...' : '결정 저장'}
                  <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                </button>

                {!hasCandidates && (
                  <>
                    <div className="decision-disabled-note">
                      <CircleAlert size={15} strokeWidth={1.9} aria-hidden="true" />
                      <span>후보 탐색 결과 연결 대기</span>
                    </div>
                    {import.meta.env.DEV && (
                      <div className="review-dev-preview">
                        <button
                          className="secondary-button"
                            type="button"
                            onClick={onGoToReceipt}
                          >
                            결과 기록 화면 확인
                          </button>
                          <p>
                            후보 탐색 결과가 연결되면 최종 결정 후 이동합니다.
                          </p>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
