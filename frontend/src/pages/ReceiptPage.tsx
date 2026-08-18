import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  FileCheck2,
  RefreshCw,
} from 'lucide-react'
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
import '../receipt.css'

interface ReceiptPageProps {
  caseData: DetectCase
  resourceConfirmation: ResourceConfirmation
  resourcePassport: ResourcePassport | null
  match: Match | null
  decision: Decision | null
  esgScenario: EsgScenario | null
  receipt: Receipt | null
  onEsgScenarioChange: (scenario: EsgScenario) => void
  onCreateReceipt: () => void
  onBackToReview: () => void
}

const decisionLabels: Record<DecisionStatus, string> = {
  APPROVED: '승인',
  HOLD: '보류',
  REJECTED: '거절',
}

const confirmationLabels: Record<ResourceConfirmation['status'], string> = {
  PENDING: '현장 확인 대기',
  CONFIRMED: '발생 확인 완료',
  NOT_CONFIRMED: '발생하지 않음',
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

const ruleValueLabel = (value: boolean | null) => {
  if (value === true) return '조건 충족'
  if (value === false) return '조건 불충족'
  return '미평가'
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
}: ReceiptPageProps) {
  const hasCandidates = Boolean(match && match.candidates.length > 0)
  const selectedCandidate = findSelectedCandidate(match, decision)
  const canCreateReceipt = Boolean(
    caseData && resourcePassport && decision && esgScenario,
  )
  const completedStepIndexes = decision ? [0, 1, 2, 3, 4] : [0, 1, 2]

  if (!decision && hasCandidates) completedStepIndexes.push(3)

  return (
    <div className="app-shell receipt-page">
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
            onClick={onBackToReview}
          >
            <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
            최종 검토로 돌아가기
          </button>
        </div>
      </header>

      <main className="page-container receipt-main" id="top">
        <WorkflowStepper
          steps={WORKFLOW_STEPS}
          activeStep={5}
          completedStepIndexes={completedStepIndexes}
        />

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
                  <strong>{hasCandidates ? match?.model : '후보 탐색 결과 연결 대기'}</strong>
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
                            <dd className={ruleValueClass(value)}>{ruleValueLabel(value)}</dd>
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
                <h2 id="esg-title">ESG 시나리오</h2>
              </div>
              <p>
                사용자 입력값과 입력된 계수를 기준으로 기존 처리 경로와 순환
                경로의 예상 차이를 계산합니다.
              </p>
            </div>
            <EsgScenarioForm
              esgScenario={esgScenario}
              onCalculate={onEsgScenarioChange}
            />
          </section>

          <section className="receipt-section green-receipt" aria-labelledby="green-receipt-title">
            <div className="receipt-section__heading">
              <div>
                <span>GREENFAB LOOP · AUDIT RECORD</span>
                <h2 id="green-receipt-title">Green Receipt</h2>
              </div>
              <p>이번 의사결정의 주요 정보를 하나의 기록으로 남깁니다.</p>
            </div>

            {receipt ? (
              <div className="receipt-complete">
                <div className="receipt-complete__title">
                  <span><CheckCircle2 size={21} aria-hidden="true" /></span>
                  <div>
                    <strong>Green Receipt 기록 완료</strong>
                    <p>{receipt.receipt_id}</p>
                  </div>
                </div>
                <dl>
                  <div><dt>생산 건</dt><dd>{receipt.case_id}</dd></div>
                  <div><dt>Resource Passport</dt><dd>{receipt.passport_id}</dd></div>
                  <div><dt>선택 후보</dt><dd>{receipt.selected_demand_id ?? '미선택'}</dd></div>
                  <div><dt>최종 결정</dt><dd>{decisionLabels[receipt.decision_status]}</dd></div>
                  <div><dt>기록 시각</dt><dd>{formatDateTime(receipt.created_at)}</dd></div>
                </dl>
                <p className="receipt-disclaimer">
                  Green Receipt는 법적 인증서가 아니라 GreenFab Loop 내부의
                  의사결정 및 이력 기록입니다.
                </p>
              </div>
            ) : (
              <div className="receipt-create">
                <span className="receipt-create__icon" aria-hidden="true">
                  <FileCheck2 size={24} strokeWidth={1.7} />
                </span>
                <div>
                  <strong>Green Receipt 생성</strong>
                  <p>
                    {esgScenario
                      ? '생산 건, Resource Passport, 사람의 최종 결정이 모두 있어야 기록을 생성할 수 있습니다.'
                      : 'ESG 시나리오 계산까지 완료하면 Green Receipt를 생성할 수 있습니다.'}
                  </p>
                </div>
                <button
                  className="primary-button receipt-create-button"
                  type="button"
                  onClick={onCreateReceipt}
                  disabled={!canCreateReceipt}
                >
                  Green Receipt 생성
                  <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                </button>
              </div>
            )}

            <button
              className="secondary-button receipt-back-button"
              type="button"
              onClick={onBackToReview}
            >
              <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
              최종 검토로 돌아가기
            </button>
          </section>
        </article>
      </main>
    </div>
  )
}
