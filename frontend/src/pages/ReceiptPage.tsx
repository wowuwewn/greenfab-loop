import { useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  FileCheck2,
  Printer,
  RefreshCw,
} from 'lucide-react'
import { toApiError, type ApiError } from '../api/client'
import { ApiErrorMessage } from '../components/ApiErrorMessage'
import { WorkflowStepper } from '../components/WorkflowStepper'
import { EsgScenarioForm } from '../components/EsgScenarioForm'
import { WORKFLOW_STEPS } from '../data/detectData'
import type {
  Decision,
  DecisionStatus,
  DetectCase,
  EsgScenario,
  Match,
  MatchCandidate,
  Receipt,
  ResourceConfirmation,
  ResourcePassport,
} from '../types/loop'
import { resolveMatchProvenance } from '../utils/matchProvenance'
import '../receipt.css'

interface ReceiptPageProps {
  caseData: DetectCase
  resourceConfirmation: ResourceConfirmation
  resourcePassport: ResourcePassport | null
  match: Match | null
  decision: Decision | null
  esgScenario: EsgScenario | null
  receipt: Receipt | null
  onEsgScenarioChange: (scenario: EsgScenario) => Promise<void>
  onCreateReceipt: () => Promise<void>
  onBackToReview: () => void
  onRestartDemo: () => Promise<void>
  onVerifyReceipt: (receiptId: string) => void
  onExitVerify: () => void
  readOnly?: boolean
}

const decisionLabels: Record<DecisionStatus, string> = {
  APPROVED: '파일럿 검토 승인',
  HOLD: '추가 확인 후 보류',
  REJECTED: '후보 제외',
}

const confirmationLabels: Record<ResourceConfirmation['status'], string> = {
  PENDING: '현장 확인 대기',
  CONFIRMED: '발생 확인 완료',
  NOT_CONFIRMED: '발생하지 않음',
}

const candidateStatusLabels: Record<MatchCandidate['status'], string> = {
  REVIEW: '✓ 검토 가능',
  NEEDS_INFO: '! 추가 정보 필요',
  RULE_FAIL: '× 조건 불충족',
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

const formatDateTime = (value: string | null) => {
  if (!value) return '기록 없음'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

const scenarioNumberFormatter = new Intl.NumberFormat('ko-KR', {
  maximumFractionDigits: 3,
})

const formatScenarioDifference = (
  value: number | null | undefined,
  unit: 'kWh' | 'kgCO₂e',
) => {
  if (value === null || value === undefined) return '계수 미입력'
  if (Math.abs(value) < 1e-10) return '변화 없음'
  if (value > 0) return `${scenarioNumberFormatter.format(value)} ${unit} 감소`
  return `${scenarioNumberFormatter.format(Math.abs(value))} ${unit} 증가`
}

const findSelectedCandidate = (
  match: Match | null,
  decision: Decision | null,
): MatchCandidate | null => {
  if (!decision?.selected_demand_id) return null

  return (
    match?.candidates.find(
      (candidate) => candidate.demand_id === decision.selected_demand_id,
    ) ?? null
  )
}

export function ReceiptPage({
  caseData,
  resourceConfirmation,
  resourcePassport,
  match,
  decision,
  esgScenario,
  receipt,
  onEsgScenarioChange,
  onCreateReceipt,
  onBackToReview,
  onRestartDemo,
  onVerifyReceipt,
  onExitVerify,
  readOnly = false,
}: ReceiptPageProps) {
  const [isRestarting, setIsRestarting] = useState(false)
  const [restartError, setRestartError] = useState<ApiError | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [receiptError, setReceiptError] = useState<ApiError | null>(null)
  const hasCandidates = Boolean(match && match.candidates.length > 0)
  const selectedCandidate = findSelectedCandidate(match, decision)
  const matchProvenance = resolveMatchProvenance(match)
  const isActualBgeRuntime = matchProvenance === 'BGE_RUNTIME'
  const isMockSnapshot = matchProvenance === 'MOCK_SNAPSHOT'
  const matchRecordTitle = hasCandidates
    ? isActualBgeRuntime
      ? 'BGE-M3 의미 검색'
      : isMockSnapshot
        ? 'Golden Demo Match snapshot'
        : '후보 탐색 결과'
    : '후보 탐색 결과 연결 대기'
  const compactResourceName =
    resourcePassport?.description
      ?.replace('반도체 세정 공정에서 회수된 DEMO ', '')
      .trim() || '자원 정보 없음'
  const compactResourceQuantity =
    resourcePassport?.quantity === null || resourcePassport?.quantity === undefined
      ? ''
      : `${scenarioNumberFormatter.format(resourcePassport.quantity)} ${
          resourcePassport.unit ?? ''
        }`.trim()
  const compactAlternativeLabel =
    selectedCandidate?.demand_id === 'D01'
      ? '세라믹 원료 파일럿 활용'
      : selectedCandidate?.demand_id === 'D15'
        ? '시험용 보조 원료 파일럿 활용'
        : selectedCandidate
          ? '선택 후보 기반 파일럿 활용'
          : esgScenario?.inputs.alternative_pathway ?? '대안 활용 방식 미입력'
  const hasEsgFactorResults = Boolean(
    esgScenario &&
      (esgScenario.results.energy_difference_kwh !== null ||
        esgScenario.results.carbon_difference_kgco2e !== null),
  )
  const defaultQuantityKg =
    resourcePassport?.unit?.trim().toLowerCase() === 'kg'
      ? resourcePassport.quantity
      : null
  const canCreateReceipt = Boolean(
    caseData && resourcePassport && decision && esgScenario,
  )
  const completedStepIndexes = decision ? [0, 1, 2, 3, 4] : [0, 1, 2]

  if (!decision && hasCandidates) completedStepIndexes.push(3)

  const restartDemo = async () => {
    if (isRestarting) return

    setIsRestarting(true)
    setRestartError(null)

    try {
      await onRestartDemo()
    } catch (error) {
      setRestartError(toApiError(error))
    } finally {
      setIsRestarting(false)
    }
  }

  const createReceipt = async () => {
    if (!canCreateReceipt || isCreating) return

    setIsCreating(true)
    setReceiptError(null)
    try {
      await onCreateReceipt()
    } catch (error) {
      setReceiptError(toApiError(error))
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <div
      className={`app-shell receipt-page${receipt ? ' receipt-page--complete' : ''}${
        readOnly ? ' receipt-page--verify' : ''
      }`}
    >
      <header className="topbar">
        <div className="page-container topbar__inner">
          <a className="brand" href="#top" aria-label="GreenFab Loop 홈">
            <span className="brand__mark" aria-hidden="true">
              <RefreshCw size={17} strokeWidth={2} />
            </span>
            <span>GreenFab Loop</span>
          </a>
          {readOnly ? (
            <button
              className="overview-back-button"
              type="button"
              onClick={onExitVerify}
            >
              <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
              Receipt로 돌아가기
            </button>
          ) : (
            <button
              className="overview-back-button"
              type="button"
              onClick={onBackToReview}
            >
              <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
              최종 검토로 돌아가기
            </button>
          )}
        </div>
      </header>

      <main
        className={`page-container receipt-main${receipt ? ' receipt-main--complete' : ''}`}
        id="top"
      >
        {!readOnly && (
          <WorkflowStepper
            steps={WORKFLOW_STEPS}
            activeStep={5}
            completedStepIndexes={completedStepIndexes}
          />
        )}

        <section className="hero-copy receipt-hero" aria-labelledby="receipt-title">
          <div className="hero-copy__main">
            <span className="eyebrow">06 · 결과 기록</span>
            <h1 id="receipt-title">결정 과정과 근거를 기록합니다</h1>
            <p>
              생산 건부터 최종 결정까지의 흐름과 ESG 시나리오 계산 근거를
              하나의 기록으로 남깁니다.
            </p>
            <p className="receipt-legal-note">
              Green Receipt는 법적 인증서가 아닌 GreenFab Loop 내부 의사결정
              기록입니다.
            </p>
          </div>
        </section>

        <article className="receipt-document">
          <section className="receipt-section decision-record" aria-labelledby="record-title">
            <div className="receipt-section__heading">
              <div>
                <span>REAL → DEMO → HUMAN</span>
                <h2 id="record-title">의사결정 기록</h2>
              </div>
              <p>AI 후보 탐색과 규칙 확인 이후 사람이 내린 결정을 기록합니다.</p>
            </div>

            <ol className="receipt-timeline">
              <li>
                <span className="receipt-timeline__marker"><Check size={13} /></span>
                <div>
                  <span className="receipt-record-label">생산 건</span>
                  <strong>{caseData.case_id}</strong>
                </div>
                <span className="receipt-badge receipt-badge--real">REAL</span>
              </li>
              <li>
                <span className="receipt-timeline__marker"><Check size={13} /></span>
                <div>
                  <span className="receipt-record-label">현장 확인</span>
                  <strong>{confirmationLabels[resourceConfirmation.status]}</strong>
                </div>
                <span className="receipt-badge receipt-badge--demo">DEMO</span>
              </li>
              <li className={resourcePassport ? '' : 'is-pending'}>
                <span className="receipt-timeline__marker">
                  {resourcePassport ? <Check size={13} /> : '—'}
                </span>
                <div>
                  <span className="receipt-record-label">자원 정보</span>
                  <strong>{resourcePassport?.passport_id ?? '자원 정보 대기'}</strong>
                </div>
                <span className="receipt-badge receipt-badge--demo">DEMO</span>
              </li>
              <li className={hasCandidates ? '' : 'is-pending'}>
                <span className="receipt-timeline__marker">
                  {hasCandidates ? <Check size={13} /> : '—'}
                </span>
                <div>
                  <span className="receipt-record-label">후보 탐색</span>
                  <strong>{matchRecordTitle}</strong>
                  {hasCandidates && match?.model && (
                    <small className="receipt-record-meta">
                      {isActualBgeRuntime
                        ? `AI RUNTIME · ${match.model} · 수요 데이터 DEMO`
                        : isMockSnapshot
                          ? `DEMO snapshot · reference model: ${match.model}`
                          : `model: ${match.model}`}
                    </small>
                  )}
                </div>
                {hasCandidates && match && (
                  <span
                    className={`receipt-badge receipt-badge--${match.source_type.toLowerCase()}`}
                  >
                    {match.source_type}
                  </span>
                )}
              </li>
              <li className={decision ? '' : 'is-pending'}>
                <span className="receipt-timeline__marker">
                  {decision ? <Check size={13} /> : '—'}
                </span>
                <div>
                  <span className="receipt-record-label">최종 결정</span>
                  <strong>
                    {decision
                      ? decisionLabels[decision.status]
                      : '최종 결정 결과를 기다리고 있습니다'}
                  </strong>
                </div>
                {decision && (
                  <span className="receipt-badge receipt-badge--human">HUMAN</span>
                )}
              </li>
            </ol>

            {!decision ? (
              <div className="receipt-waiting-message">
                <strong>최종 결정 결과를 기다리고 있습니다</strong>
                <p>
                  후보 탐색과 담당자 최종 결정이 완료되면 Green Receipt를 생성할
                  수 있습니다.
                </p>
              </div>
            ) : (
              <div className="receipt-record-details">
                <div className="decision-summary">
                  <h3>사람의 최종 결정</h3>
                  <dl>
                    <div><dt>결정 상태</dt><dd>{decisionLabels[decision.status]}</dd></div>
                    <div><dt>선택 후보</dt><dd>{decision.selected_demand_id ?? '선택 후보 없음'}</dd></div>
                    <div><dt>결정 사유</dt><dd>{decision.reason ?? '미입력'}</dd></div>
                    <div><dt>결정자</dt><dd>{decision.decided_by}</dd></div>
                    <div><dt>결정 시각</dt><dd>{formatDateTime(decision.decided_at)}</dd></div>
                  </dl>
                </div>

                {selectedCandidate && (
                  <div className="selected-match-summary">
                    <div className="selected-match-summary__heading">
                      <div>
                        <span>AI + RULE</span>
                        <h3>선택된 활용 후보</h3>
                      </div>
                      {selectedCandidate.semantic_similarity !== null && (
                        <strong>
                          의미 유사도 {selectedCandidate.semantic_similarity.toFixed(3)}
                        </strong>
                      )}
                    </div>
                    <dl className="candidate-identity">
                      <div><dt>회사명</dt><dd>{selectedCandidate.company_name}</dd></div>
                      <div><dt>수요 설명</dt><dd>{selectedCandidate.demand_description}</dd></div>
                    </dl>
                    <dl className="receipt-rule-results">
                      {ruleLabels.map(([key, label]) => {
                        const value = selectedCandidate.rule_check[key]
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
                    {selectedCandidate.rule_check.missing_fields &&
                      selectedCandidate.rule_check.missing_fields.length > 0 && (
                        <p className="receipt-missing-fields">
                          <strong>추가 확인 정보</strong>
                          {selectedCandidate.rule_check.missing_fields
                            .map((field) => fieldLabels[field] ?? field)
                            .join(', ')}
                        </p>
                      )}
                  </div>
                )}
              </div>
            )}
          </section>

          <section className="receipt-section esg-record" aria-labelledby="esg-title">
            <div className="receipt-section__heading receipt-section__heading--inline">
              <div>
                <span className="receipt-badge receipt-badge--scenario">SCENARIO</span>
                <h2 id="esg-title">이 자원을 다른 방식으로 활용한다면?</h2>
              </div>
              <p>
                현재 처리 방식과 선택한 활용 후보를 비교하는 가정 시나리오입니다.
                실제 감축량이나 AI 예측값이 아닙니다.
              </p>
            </div>
            {!readOnly && (
              <EsgScenarioForm
                esgScenario={esgScenario}
                defaultQuantityKg={defaultQuantityKg}
                selectedCandidate={selectedCandidate}
                decisionStatus={decision?.status ?? null}
                onCalculate={onEsgScenarioChange}
              />
            )}
          </section>

          <section className="receipt-section green-receipt" aria-labelledby="green-receipt-title">
            <div className="receipt-section__heading">
              <div>
                <span>결과 요약</span>
                <h2 id="green-receipt-title">Green Receipt</h2>
              </div>
              <p>지금까지의 확인 내용과 담당자 결정을 한 장으로 정리합니다.</p>
            </div>

            {receipt ? (
              <div className="receipt-complete-wrap">
                <div className="receipt-complete" aria-live="polite">
                  <header className="receipt-complete__title">
                    <span><CheckCircle2 size={20} strokeWidth={1.8} aria-hidden="true" /></span>
                    <div>
                      <small>GREENFAB LOOP</small>
                      <strong>GREEN RECEIPT</strong>
                      <p>자원 활용 의사결정 기록</p>
                    </div>
                  </header>

                  <section className="receipt-paper-section" aria-labelledby="receipt-resource-title">
                    <div className="receipt-paper-section__heading">
                      <h3 id="receipt-resource-title">검토 기록</h3>
                    </div>
                    <dl className="receipt-paper-lines">
                      <div>
                        <dt>Receipt ID</dt>
                        <dd><strong>{receipt.receipt_id}</strong></dd>
                      </div>
                      <div>
                        <dt>생산 건</dt>
                        <dd className="receipt-paper-inline">
                          <strong>{receipt.case_id}</strong>
                          <span className="receipt-badge receipt-badge--real">REAL</span>
                        </dd>
                      </div>
                      <div>
                        <dt>확인된 자원</dt>
                        <dd className="receipt-paper-inline">
                          <strong className="receipt-paper-key-value">
                            {compactResourceName}
                            {compactResourceQuantity && ` · ${compactResourceQuantity}`}
                          </strong>
                          <span className="receipt-badge receipt-badge--demo">DEMO</span>
                        </dd>
                      </div>
                    </dl>
                  </section>

                  <section className="receipt-paper-section" aria-labelledby="receipt-match-title">
                    <div className="receipt-paper-section__heading">
                      <h3 id="receipt-match-title">후보 탐색</h3>
                      <span className="receipt-paper-section__badges">
                        <span className={`receipt-badge receipt-badge--${isActualBgeRuntime ? 'ai' : 'demo'}`}>
                          {isActualBgeRuntime ? 'AI' : 'DEMO'}
                        </span>
                        <span className="receipt-badge receipt-badge--rule">RULE</span>
                      </span>
                    </div>
                    <dl className="receipt-paper-lines">
                      <div>
                        <dt>선택 후보</dt>
                        <dd>
                          {selectedCandidate ? (
                            <>
                              <strong className="receipt-paper-key-value">
                                {selectedCandidate.company_name} · {selectedCandidate.demand_id}
                              </strong>
                              <span className="receipt-paper-facts">
                                <span>
                                  의미 유사도{' '}
                                  <b>
                                    {selectedCandidate.semantic_similarity === null
                                      ? '계산값 없음'
                                      : selectedCandidate.semantic_similarity.toFixed(3)}
                                  </b>
                                </span>
                                <span>조건 확인 · <b>{candidateStatusLabels[selectedCandidate.status]}</b></span>
                              </span>
                              <small className="receipt-paper-note">
                                문장 의미 기반 후보 탐색 결과이며 적합도·안전성·성공 확률을 의미하지 않습니다.
                              </small>
                            </>
                          ) : (
                            <strong>선택 후보 없음</strong>
                          )}
                        </dd>
                      </div>
                    </dl>
                  </section>

                  <section className="receipt-paper-section" aria-labelledby="receipt-decision-title">
                    <div className="receipt-paper-section__heading">
                      <h3 id="receipt-decision-title">최종 결정</h3>
                      <span className="receipt-badge receipt-badge--human">HUMAN</span>
                    </div>
                    <dl className="receipt-paper-lines">
                      <div>
                        <dt>담당자 판단</dt>
                        <dd className="receipt-paper-decision">
                          <strong>{decisionLabels[receipt.decision_status]}</strong>
                        </dd>
                      </div>
                      <div>
                        <dt>결정 사유</dt>
                        <dd>{decision?.reason ?? '결정 사유 미입력'}</dd>
                      </div>
                    </dl>
                  </section>

                  <section className="receipt-paper-section" aria-labelledby="receipt-esg-title">
                    <div className="receipt-paper-section__heading">
                      <h3 id="receipt-esg-title">ESG 시나리오</h3>
                      <span className="receipt-badge receipt-badge--scenario">SCENARIO</span>
                    </div>
                    {esgScenario ? (
                      <dl className="receipt-paper-lines">
                        <div>
                          <dt>가정 비교</dt>
                          <dd className="receipt-paper-pathway">
                            <span>{esgScenario.inputs.baseline_pathway}</span>
                            <ArrowRight size={14} strokeWidth={1.8} aria-hidden="true" />
                            <strong>{compactAlternativeLabel}</strong>
                          </dd>
                        </div>
                        <div>
                          <dt>적용 자원량</dt>
                          <dd>
                            <strong className="receipt-paper-quantity">
                              {scenarioNumberFormatter.format(
                                esgScenario.results.diverted_quantity_kg,
                              )}{' '}
                              kg
                            </strong>
                            <small className="receipt-paper-note">
                              {hasEsgFactorResults
                                ? `${formatScenarioDifference(
                                    esgScenario.results.energy_difference_kwh,
                                    'kWh',
                                  )} · ${formatScenarioDifference(
                                    esgScenario.results.carbon_difference_kgco2e,
                                    'kgCO₂e',
                                  )}`
                                : '에너지·탄소 차이는 계수 미입력으로 산출하지 않음'}
                            </small>
                          </dd>
                        </div>
                      </dl>
                    ) : (
                      <p className="receipt-paper-empty">기록된 ESG 시나리오가 없습니다.</p>
                    )}
                  </section>

                  <footer className="receipt-paper-footer">
                    <span>담당자 · {decision?.decided_by ?? '기록 없음'}</span>
                    <time dateTime={decision?.decided_at ?? receipt.created_at ?? undefined}>
                      {decision
                        ? formatDateTime(decision.decided_at)
                        : formatDateTime(receipt.created_at)}
                    </time>
                    <p>
                      Green Receipt는 내부 의사결정 기록이며 법적·안전성·재활용 인증서가 아닙니다.
                    </p>
                  </footer>
                </div>
                {!readOnly && (
                  <div className="receipt-restart">
                    <ApiErrorMessage
                      error={restartError}
                      message={
                        restartError?.status === 404 && restartError.code === 'NOT_FOUND'
                          ? '백엔드의 데모 초기화 기능이 비활성화되어 있습니다.'
                          : undefined
                      }
                    />
                    <div className="receipt-complete-actions">
                      <button
                        className="primary-button receipt-review-button"
                        type="button"
                        onClick={onBackToReview}
                      >
                        <ArrowLeft size={15} strokeWidth={1.8} aria-hidden="true" />
                        최종 검토로 돌아가기
                      </button>
                      <button
                        className="secondary-button receipt-print-button"
                        type="button"
                        onClick={() => window.print()}
                      >
                        <Printer size={15} strokeWidth={1.8} aria-hidden="true" />
                        PDF 저장 / 인쇄
                      </button>
                      <a
                        className="secondary-button receipt-verify-link"
                        href={`#/verify/${encodeURIComponent(receipt.receipt_id)}`}
                        onClick={(event) => {
                          event.preventDefault()
                          onVerifyReceipt(receipt.receipt_id)
                        }}
                      >
                        Receipt 다시 확인하기
                      </a>
                      <button
                        className="secondary-button receipt-restart-button"
                        type="button"
                        onClick={restartDemo}
                        disabled={isRestarting}
                      >
                        <RefreshCw size={15} strokeWidth={1.8} aria-hidden="true" />
                        {isRestarting ? '데모를 초기화하고 있습니다...' : '데모 처음부터 다시'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="receipt-create">
                <span className="receipt-create__icon" aria-hidden="true">
                  <FileCheck2 size={24} strokeWidth={1.7} />
                </span>
                <div>
                  <strong>검토 결과 요약 만들기</strong>
                  <p>
                    {esgScenario
                      ? '생산 건, 자원 정보, 담당자 최종 결정이 모두 있어야 요약을 만들 수 있습니다.'
                      : '위에서 가정 비교까지 계산하면 검토 결과 요약을 만들 수 있습니다.'}
                  </p>
                  <ApiErrorMessage error={receiptError} />
                </div>
                <button
                  className="primary-button receipt-create-button"
                  type="button"
                  onClick={createReceipt}
                  disabled={!canCreateReceipt || isCreating}
                >
                  {isCreating ? '기록을 저장하고 있습니다...' : '검토 결과 요약 보기'}
                  <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                </button>
              </div>
            )}

            {!readOnly && (
              <button
                className="secondary-button receipt-back-button"
                type="button"
                onClick={onBackToReview}
              >
                <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
                최종 검토로 돌아가기
              </button>
            )}
          </section>
        </article>
      </main>
    </div>
  )
}
