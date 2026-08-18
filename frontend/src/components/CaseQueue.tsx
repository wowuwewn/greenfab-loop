import { useMemo, useState } from 'react'
import {
  ArrowRight,
  CheckCircle2,
  CircleX,
  Flag,
  Search,
} from 'lucide-react'
import { toApiError, type ApiError } from '../api/client'
import type { CaseSummary, WorkflowStatus } from '../types/loop'
import {
  getCaseWorkflowPresentation,
  GOLDEN_CASE_ID,
  isActionableCase,
} from '../workflow'
import { ApiErrorMessage } from './ApiErrorMessage'
import {
  filterCaseSummaries,
  type CaseFilter,
} from './caseQueueFilters'

export interface CaseQueueProps {
  cases: CaseSummary[]
  recommendedCaseId: string | null
  selectedCaseId: string | null
  isLoading: boolean
  onOpenCase: (summary: CaseSummary) => Promise<void>
}

const filters: Array<{ value: CaseFilter; label: string }> = [
  { value: 'all', label: '전체' },
  { value: 'actionable', label: '조치 필요' },
  { value: 'complete', label: '기록 완료' },
  { value: 'closed', label: '종료' },
]

const closedStatuses: WorkflowStatus[] = ['NOT_CONFIRMED', 'CLOSED']

const isClosedCase = (summary: CaseSummary) =>
  closedStatuses.includes(summary.workflow_status)

const formatUpdatedAt = (value: string) => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '업데이트 시간 미확인'

  return new Intl.DateTimeFormat('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function CaseQueue({
  cases,
  recommendedCaseId,
  selectedCaseId,
  isLoading,
  onOpenCase,
}: CaseQueueProps) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<CaseFilter>('all')
  const [openingCaseId, setOpeningCaseId] = useState<string | null>(null)
  const [apiError, setApiError] = useState<ApiError | null>(null)

  const recommendedCase = useMemo(
    () => cases.find((item) => item.case_id === recommendedCaseId) ?? null,
    [cases, recommendedCaseId],
  )

  const counts = useMemo(
    () => ({
      all: cases.length,
      actionable: cases.filter(isActionableCase).length,
      complete: cases.filter(
        (item) => item.workflow_status === 'RECEIPT_CREATED',
      ).length,
      closed: cases.filter(isClosedCase).length,
    }),
    [cases],
  )

  const visibleCases = useMemo(
    () => filterCaseSummaries(cases, filter, query),
    [cases, filter, query],
  )

  const openCase = async (summary: CaseSummary) => {
    setOpeningCaseId(summary.case_id)
    setApiError(null)

    try {
      await onOpenCase(summary)
    } catch (error) {
      setApiError(toApiError(error))
    } finally {
      setOpeningCaseId(null)
    }
  }

  const recommendedPresentation = recommendedCase
    ? getCaseWorkflowPresentation(recommendedCase.workflow_status)
    : null
  const recommendationIsActionable = recommendedCase
    ? isActionableCase(recommendedCase)
    : false
  const isGoldenRecommendation =
    recommendationIsActionable && recommendedCaseId === GOLDEN_CASE_ID

  return (
    <section className="case-queue" aria-labelledby="case-queue-title">
      <div className="case-queue__heading">
        <div>
          <span className="overview-eyebrow">OPERATIONS QUEUE</span>
          <h2 id="case-queue-title">위험 Case 운영 현황</h2>
          <p>
            모델이 선별한 위험 건을 조회하고, Case별 다음 검토 단계를 이어갑니다.
          </p>
        </div>
        <span className="case-queue__scope">검토 큐 · 상위 {cases.length}건</span>
      </div>

      <dl className="case-queue__kpis" aria-label="Case 현황 요약">
        <div>
          <dt>선별 위험 Case</dt>
          <dd>{counts.all}</dd>
        </div>
        <div>
          <dt>조치 필요</dt>
          <dd>{counts.actionable}</dd>
        </div>
        <div>
          <dt>Green Receipt 완료</dt>
          <dd>{counts.complete}</dd>
        </div>
        <div>
          <dt>자원 미발생 · 종료</dt>
          <dd>{counts.closed}</dd>
        </div>
      </dl>

      {recommendedCase && recommendedPresentation ? (
        <div
          className={`case-recommendation${
            recommendationIsActionable ? '' : ' is-history'
          }`}
        >
          <span className="case-recommendation__icon" aria-hidden="true">
            {recommendationIsActionable ? (
              <Flag size={20} strokeWidth={1.8} />
            ) : (
              <CheckCircle2 size={20} strokeWidth={1.8} />
            )}
          </span>
          <div className="case-recommendation__copy">
            <span className="case-recommendation__label">
              {isGoldenRecommendation
                ? '시연 추천 Case'
                : recommendationIsActionable
                  ? '대체 시작 Case'
                  : '기록 열람 Case'}
            </span>
            <strong>{recommendedCase.case_id}</strong>
            <p>
              {isGoldenRecommendation
                ? 'Golden Demo 기준 Case입니다. 위험 근거부터 전체 흐름을 확인할 수 있습니다.'
                : recommendationIsActionable
                  ? `${GOLDEN_CASE_ID}의 처리가 종료되어 현재 진행 가능한 Case를 안내합니다.`
                  : '진행 가능한 Case가 없어 완료된 기록을 안내합니다.'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => openCase(recommendedCase)}
            disabled={openingCaseId !== null}
          >
            {openingCaseId === recommendedCase.case_id
              ? '불러오는 중...'
              : recommendedPresentation.nextAction}
            <ArrowRight size={17} strokeWidth={1.9} aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <div className="case-queue__toolbar">
        <label className="case-search">
          <Search size={18} strokeWidth={1.8} aria-hidden="true" />
          <span className="sr-only">Case 검색</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Case ID 또는 상태 검색"
          />
        </label>

        <div className="case-filters" aria-label="Case 상태 필터">
          {filters.map((item) => (
            <button
              className={filter === item.value ? 'is-active' : undefined}
              type="button"
              key={item.value}
              onClick={() => setFilter(item.value)}
              aria-pressed={filter === item.value}
            >
              {item.label}
              <span>{counts[item.value]}</span>
            </button>
          ))}
        </div>
      </div>

      <ApiErrorMessage error={apiError} />

      <div className="case-table-wrap" aria-live="polite" aria-busy={isLoading}>
        {isLoading ? (
          <div className="case-queue__loading" role="status">
            <span className="case-queue__spinner" aria-hidden="true" />
            Case 목록을 불러오고 있습니다.
          </div>
        ) : visibleCases.length > 0 ? (
          <table className="case-table">
            <thead>
              <tr>
                <th scope="col">우선순위</th>
                <th scope="col">Case</th>
                <th scope="col">현재 상태</th>
                <th scope="col">업데이트</th>
                <th scope="col">다음 단계</th>
                <th scope="col">
                  <span className="sr-only">Case 열기</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleCases.map((summary) => {
                const presentation = getCaseWorkflowPresentation(
                  summary.workflow_status,
                )
                const isRecommended = summary.case_id === recommendedCaseId
                const isSelected = summary.case_id === selectedCaseId
                const isOpening = summary.case_id === openingCaseId

                return (
                  <tr
                    className={`${isSelected ? 'is-selected' : ''}${
                      isRecommended ? ' is-recommended' : ''
                    }`}
                    key={summary.case_id}
                  >
                    <td data-label="우선순위">
                      <span className="case-rank">
                        {summary.risk_rank === null
                          ? '순위 없음'
                          : `${summary.risk_rank}위`}
                      </span>
                    </td>
                    <td data-label="Case">
                      <div className="case-identity">
                        <strong>{summary.case_id}</strong>
                        <span className="case-source">
                          {summary.source_type}
                        </span>
                        {isRecommended ? (
                          <span className="case-recommended-badge">
                            {isGoldenRecommendation
                              ? '시연 추천'
                              : recommendationIsActionable
                                ? '대체'
                                : '기록'}
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td data-label="현재 상태">
                      <span
                        className={`case-status is-${presentation.tone}`}
                      >
                        {presentation.tone === 'closed' ? (
                          <CircleX size={14} strokeWidth={2} aria-hidden="true" />
                        ) : presentation.tone === 'complete' ? (
                          <CheckCircle2
                            size={14}
                            strokeWidth={2}
                            aria-hidden="true"
                          />
                        ) : null}
                        {presentation.label}
                      </span>
                    </td>
                    <td data-label="업데이트">
                      <time dateTime={summary.updated_at}>
                        {formatUpdatedAt(summary.updated_at)}
                      </time>
                    </td>
                    <td data-label="다음 단계">
                      <span className="case-next-action">
                        {presentation.nextAction}
                      </span>
                    </td>
                    <td className="case-table__action">
                      <button
                        type="button"
                        onClick={() => openCase(summary)}
                        disabled={openingCaseId !== null}
                        aria-label={`${summary.case_id} ${presentation.nextAction}`}
                      >
                        {isOpening ? '불러오는 중...' : presentation.nextAction}
                        <ArrowRight
                          size={16}
                          strokeWidth={1.9}
                          aria-hidden="true"
                        />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div className="case-queue__empty">
            <Search size={24} strokeWidth={1.6} aria-hidden="true" />
            <strong>조건에 맞는 Case가 없습니다.</strong>
            <p>검색어를 지우거나 다른 상태 필터를 선택해주세요.</p>
          </div>
        )}
      </div>
    </section>
  )
}
