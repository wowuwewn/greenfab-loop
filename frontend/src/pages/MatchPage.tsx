import { useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  CheckCircle2,
  FileText,
  ListChecks,
  RefreshCw,
  Search,
  UserCheck,
} from 'lucide-react'
import { toApiError, type ApiError } from '../api/client'
import { ApiErrorMessage } from '../components/ApiErrorMessage'
import { WorkflowStepper } from '../components/WorkflowStepper'
import { WORKFLOW_STEPS } from '../data/detectData'
import type {
  Match,
  MatchCandidate,
  ResourcePassport,
} from '../types/loop'
import { resolveMatchProvenance } from '../utils/matchProvenance'
import '../match.css'

interface MatchPageProps {
  resourcePassport: ResourcePassport | null
  match: Match | null
  onRunMatch: () => Promise<void>
  onBackToPassport: () => void
  onGoToReview: () => void
}

const candidateStatusLabels: Record<MatchCandidate['status'], string> = {
  REVIEW: '검토 가능',
  NEEDS_INFO: '추가 정보 필요',
  RULE_FAIL: '조건 불충족',
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

export function MatchPage({
  resourcePassport,
  match,
  onRunMatch,
  onBackToPassport,
  onGoToReview,
}: MatchPageProps) {
  const [isMatching, setIsMatching] = useState(false)
  const [apiError, setApiError] = useState<ApiError | null>(null)
  const candidates = match?.candidates ?? []
  const hasCandidates = candidates.length > 0
  const showCandidates = hasCandidates && apiError === null && !isMatching
  const matchProvenance = resolveMatchProvenance(match)
  const isActualBgeRuntime = matchProvenance === 'BGE_RUNTIME'
  const isMockSnapshot = matchProvenance === 'MOCK_SNAPSHOT'

  const handleRunMatch = async () => {
    if (!resourcePassport || isMatching) return

    setIsMatching(true)
    setApiError(null)

    try {
      await onRunMatch()
    } catch (error) {
      setApiError(toApiError(error))
    } finally {
      setIsMatching(false)
    }
  }

  return (
    <div className="app-shell match-page">
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
            onClick={onBackToPassport}
          >
            <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
            자원 정보로 돌아가기
          </button>
        </div>
      </header>

      <main className="page-container match-main" id="top">
        <WorkflowStepper
          steps={WORKFLOW_STEPS}
          activeStep={3}
          completedStepIndexes={[0, 1, 2]}
        />

        <section className="hero-copy match-hero" aria-labelledby="match-title">
          <div className="hero-copy__main">
            <span className="eyebrow">04 · 후보 탐색</span>
            <h1 id="match-title">의미가 가까운 활용 후보를 찾습니다</h1>
            <p>
              Resource Passport의 자원 설명을 바탕으로 의미가 가까운 수요 후보를
              탐색합니다.
            </p>
          </div>
        </section>

        <section className="match-passport" aria-labelledby="match-passport-title">
          <div className="match-passport__title">
            <span aria-hidden="true"><FileText size={19} strokeWidth={1.8} /></span>
            <div>
              <small>DEMO · RESOURCE PASSPORT</small>
              <h2 id="match-passport-title">현재 자원 정보</h2>
            </div>
          </div>
          {resourcePassport ? (
            <dl>
              <div><dt>자원 설명</dt><dd>{resourcePassport.description}</dd></div>
              <div>
                <dt>수량</dt>
                <dd>
                  {resourcePassport.quantity === null
                    ? '미입력'
                    : `${resourcePassport.quantity} ${resourcePassport.unit ?? ''}`.trim()}
                </dd>
              </div>
              <div><dt>현재 상태</dt><dd>{resourcePassport.condition ?? '미입력'}</dd></div>
              <div><dt>위치</dt><dd>{resourcePassport.location ?? '미입력'}</dd></div>
            </dl>
          ) : (
            <p className="match-passport__empty">저장된 자원 정보가 없습니다.</p>
          )}
        </section>

        <section
          className={`match-process${isMatching ? ' is-matching' : ''}`}
          aria-label="후보 탐색과 최종 결정의 역할"
        >
          <div className="match-process__step">
            <FileText size={17} aria-hidden="true" />
            <span><strong>자원 정보</strong><small>Resource Passport</small></span>
          </div>
          <ArrowRight className="match-process__arrow" size={15} aria-hidden="true" />
          <div className="match-process__step">
            <Bot size={17} aria-hidden="true" />
            <span><strong>의미 검색</strong><small>AI</small></span>
          </div>
          <ArrowRight className="match-process__arrow" size={15} aria-hidden="true" />
          <div className="match-process__step">
            <Search size={17} aria-hidden="true" />
            <span><strong>상위 후보</strong><small>Top-3</small></span>
          </div>
          <ArrowRight className="match-process__arrow" size={15} aria-hidden="true" />
          <div className="match-process__step">
            <ListChecks size={17} aria-hidden="true" />
            <span><strong>조건 확인</strong><small>RULE</small></span>
          </div>
          <ArrowRight className="match-process__arrow" size={15} aria-hidden="true" />
          <div className="match-process__step">
            <UserCheck size={17} aria-hidden="true" />
            <span><strong>담당자 결정</strong><small>HUMAN</small></span>
          </div>
          <p>AI가 자동 승인하지 않습니다.</p>
        </section>

        <section className="match-results" aria-labelledby="match-results-title">
          <div className="match-results__heading">
            <div>
              <span>후보 탐색 + 조건 확인</span>
              <h2 id="match-results-title">활용 후보 탐색 결과</h2>
              <p>
                의미 유사도는 문장 의미가 얼마나 가까운지를 나타내며,
                산업 적합도·안전성·재활용 성공 확률을 의미하지 않습니다.
              </p>
            </div>
            <button
              className="primary-button match-run-button"
              type="button"
              onClick={handleRunMatch}
              disabled={!resourcePassport || isMatching}
            >
              {isMatching ? '후보를 확인하고 있습니다...' : '활용 후보 찾기'}
              <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
            </button>
          </div>

          {isMatching && (
            <div className="match-loading" role="status" aria-live="polite">
              <div className="match-search-visual" aria-hidden="true">
                <span className="match-search-visual__line match-search-visual__line--one" />
                <span className="match-search-visual__line match-search-visual__line--two" />
                <span className="match-search-visual__line match-search-visual__line--three" />
                <span className="match-search-visual__line match-search-visual__line--four" />
                <span className="match-search-visual__center"><FileText size={24} strokeWidth={1.7} /></span>
                <span className="match-search-visual__candidate match-search-visual__candidate--one" />
                <span className="match-search-visual__candidate match-search-visual__candidate--two" />
                <span className="match-search-visual__candidate match-search-visual__candidate--three" />
                <span className="match-search-visual__candidate match-search-visual__candidate--four" />
              </div>
              <div>
                <strong>의미가 가까운 후보를 확인하고 있습니다.</strong>
                <p>저장된 자원 정보를 기준으로 후보와 조건을 정리하고 있습니다.</p>
              </div>
            </div>
          )}

          <ApiErrorMessage
            error={apiError}
            onRetry={handleRunMatch}
            retryDisabled={isMatching}
          />

          {showCandidates ? (
            <>
              <div className="match-complete-feedback" role="status">
                <CheckCircle2 size={17} strokeWidth={1.9} aria-hidden="true" />
                <strong>후보 탐색 결과 {candidates.length}건을 정리했습니다.</strong>
              </div>
              <div className="match-candidate-list">
                {candidates.map((candidate, index) => (
                  <article
                    className={`match-candidate match-candidate--${candidate.status.toLowerCase()}`}
                    key={candidate.demand_id}
                    style={{ animationDelay: `${index * 90}ms` }}
                  >
                    <div className="match-candidate__topline">
                      <span>{index + 1}순위</span>
                      <span className={`candidate-status candidate-status--${candidate.status.toLowerCase()}`}>
                        {candidateStatusLabels[candidate.status]}
                      </span>
                    </div>
                    <div className="match-candidate__identity">
                      <div>
                        <strong>{candidate.company_name}</strong>
                        <small>{candidate.demand_id}</small>
                      </div>
                    </div>
                    <div className="match-similarity">
                      <div>
                        <span>의미 유사도</span>
                        <strong>
                          {candidate.semantic_similarity === null
                            ? '계산값 없음'
                            : candidate.semantic_similarity.toFixed(3)}
                        </strong>
                      </div>
                      {candidate.semantic_similarity !== null && (
                        <span
                          className="match-similarity__track"
                          role="meter"
                          aria-label={`문장 의미 유사도 ${candidate.semantic_similarity.toFixed(3)}`}
                          aria-valuemin={-1}
                          aria-valuemax={1}
                          aria-valuenow={candidate.semantic_similarity}
                        >
                          <span
                            style={{
                              transform: `scaleX(${Math.max(0, Math.min(1, candidate.semantic_similarity))})`,
                            }}
                          />
                        </span>
                      )}
                    </div>
                    <p>{candidate.demand_description}</p>
                    <dl className="match-rule-results">
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
                        <div className="match-missing-fields">
                          <strong>추가 확인 필요</strong>
                          <span>
                            누락 정보: {candidate.rule_check.missing_fields
                              .map((field) => fieldLabels[field] ?? field)
                              .join(', ')}
                          </span>
                        </div>
                      )}
                  </article>
                ))}
              </div>
              <p className="match-rule-help">
                미평가: 해당 후보에 적용할 조건이 없거나 현재 정보로 평가하지 않은 항목
              </p>
              <div className="match-result-actions">
                <div className="match-provenance">
                  <span className={`source-badge source-badge--${match?.source_type.toLowerCase()}`}>
                    {match?.source_type === 'DEMO' ? 'DEMO 수요' : match?.source_type}
                  </span>
                  <div>
                    <strong>
                      {isActualBgeRuntime
                        ? 'AI · BGE-M3 의미 검색'
                        : isMockSnapshot
                          ? 'DEMO · Golden Demo Match snapshot'
                          : '후보 탐색 결과'}
                    </strong>
                    <small>
                      {isActualBgeRuntime
                        ? 'Resource Passport 설명을 실제 BGE-M3 임베딩으로 변환해 DEMO 수요 후보를 탐색했습니다.'
                        : isMockSnapshot
                          ? '현재 데모에서는 사전 생성된 후보 결과를 사용합니다.'
                          : '연결된 후보 탐색 결과입니다.'}
                    </small>
                    {match?.model && (
                      <small className="match-provenance__technical">
                        {isActualBgeRuntime ? 'runtime model' : 'reference model'}: {match.model}
                        {match.model_revision ? ` · ${match.model_revision}` : ''}
                      </small>
                    )}
                  </div>
                </div>
                <button
                  className="primary-button match-review-button"
                  type="button"
                  onClick={onGoToReview}
                >
                  최종 검토로 이동
                  <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
                </button>
              </div>
            </>
          ) : (
            !isMatching && !apiError && (
              <div className="match-empty">
                <span aria-hidden="true"><Search size={24} strokeWidth={1.7} /></span>
                <strong>아직 실행된 후보 탐색이 없습니다</strong>
                <p>저장된 자원 정보를 기준으로 후보 탐색을 실행해주세요.</p>
              </div>
            )
          )}
        </section>
      </main>
    </div>
  )
}
