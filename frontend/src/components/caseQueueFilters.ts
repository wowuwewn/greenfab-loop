import type { CaseSummary } from '../types/loop'
import {
  getCaseWorkflowPresentation,
  isActionableCase,
} from '../workflow'

export type CaseFilter = 'all' | 'actionable' | 'complete' | 'closed'

const isClosedCase = (summary: CaseSummary) =>
  summary.workflow_status === 'NOT_CONFIRMED' ||
  summary.workflow_status === 'CLOSED'

const matchesFilter = (summary: CaseSummary, filter: CaseFilter) => {
  if (filter === 'actionable') return isActionableCase(summary)
  if (filter === 'complete') return summary.workflow_status === 'RECEIPT_CREATED'
  if (filter === 'closed') return isClosedCase(summary)
  return true
}

export const filterCaseSummaries = (
  cases: CaseSummary[],
  filter: CaseFilter,
  query: string,
) => {
  const normalizedQuery = query.trim().toLocaleLowerCase('ko-KR')

  return cases.filter((summary) => {
    if (!matchesFilter(summary, filter)) return false
    if (!normalizedQuery) return true

    const presentation = getCaseWorkflowPresentation(summary.workflow_status)
    return [
      summary.case_id,
      summary.source_type,
      summary.workflow_status,
      presentation.label,
      presentation.nextAction,
    ]
      .join(' ')
      .toLocaleLowerCase('ko-KR')
      .includes(normalizedQuery)
  })
}
