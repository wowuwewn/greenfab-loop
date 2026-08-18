import { ApiError } from './api/client'
import type {
  CaseEnvelope,
  CaseSummary,
  WorkflowStatus,
} from './types/loop'

export type IdempotentAction = 'match' | 'receipt'
export type CaseDetailView =
  | 'detect'
  | 'confirm'
  | 'passport'
  | 'match'
  | 'review'
  | 'receipt'

export const GOLDEN_CASE_ID = 'SECOM-0116'

export interface CaseWorkflowPresentation {
  label: string
  nextAction: string
  view: CaseDetailView
  tone: 'pending' | 'active' | 'complete' | 'closed'
  readOnly: boolean
}

const workflowPresentation = {
  DETECTED: {
    label: '위험 신호 감지',
    nextAction: '위험 근거 확인',
    view: 'detect',
    tone: 'pending',
    readOnly: false,
  },
  CONFIRMATION_PENDING: {
    label: '현장 확인 대기',
    nextAction: '발생 여부 확인',
    view: 'confirm',
    tone: 'pending',
    readOnly: false,
  },
  RESOURCE_CONFIRMED: {
    label: '자원 발생 확인',
    nextAction: 'Passport 작성',
    view: 'passport',
    tone: 'active',
    readOnly: false,
  },
  PASSPORT_READY: {
    label: 'Passport 저장',
    nextAction: 'AI 후보 찾기',
    view: 'match',
    tone: 'active',
    readOnly: false,
  },
  MATCH_READY: {
    label: '후보 탐색 완료',
    nextAction: '사람 검토·결정',
    view: 'review',
    tone: 'active',
    readOnly: false,
  },
  DECIDED: {
    label: '최종 결정 저장',
    nextAction: 'ESG Scenario 생성',
    view: 'receipt',
    tone: 'active',
    readOnly: false,
  },
  SCENARIO_READY: {
    label: 'Scenario 준비',
    nextAction: 'Green Receipt 생성',
    view: 'receipt',
    tone: 'active',
    readOnly: false,
  },
  RECEIPT_CREATED: {
    label: '기록 완료',
    nextAction: 'Green Receipt 보기',
    view: 'receipt',
    tone: 'complete',
    readOnly: true,
  },
  NOT_CONFIRMED: {
    label: '자원 미발생',
    nextAction: '종료 내역 보기',
    view: 'confirm',
    tone: 'closed',
    readOnly: true,
  },
  CLOSED: {
    label: '자원 미발생 · 종료',
    nextAction: '종료 내역 보기',
    view: 'confirm',
    tone: 'closed',
    readOnly: true,
  },
} satisfies Record<WorkflowStatus, CaseWorkflowPresentation>

const recommendationOrder: WorkflowStatus[] = [
  'CONFIRMATION_PENDING',
  'DETECTED',
  'RESOURCE_CONFIRMED',
  'PASSPORT_READY',
  'MATCH_READY',
  'DECIDED',
  'SCENARIO_READY',
]

const compareCases = (left: CaseSummary, right: CaseSummary) => {
  const leftRank = left.risk_rank ?? Number.POSITIVE_INFINITY
  const rightRank = right.risk_rank ?? Number.POSITIVE_INFINITY
  if (leftRank !== rightRank) return leftRank - rightRank

  const updatedDifference =
    new Date(left.updated_at).getTime() - new Date(right.updated_at).getTime()
  if (updatedDifference !== 0) return updatedDifference
  return left.case_id.localeCompare(right.case_id)
}

export const getCaseWorkflowPresentation = (status: WorkflowStatus) =>
  workflowPresentation[status]

export const isActionableCase = (summary: CaseSummary) =>
  !workflowPresentation[summary.workflow_status].readOnly

export const deriveWorkflowStatus = (
  envelope: CaseEnvelope,
): WorkflowStatus => {
  if (envelope.receipt) return 'RECEIPT_CREATED'
  if (envelope.esg_scenario) return 'SCENARIO_READY'
  if (envelope.decision) return 'DECIDED'
  if (envelope.match) return 'MATCH_READY'
  if (envelope.resource_passport) return 'PASSPORT_READY'
  if (envelope.resource_confirmation.status === 'NOT_CONFIRMED') return 'CLOSED'
  if (envelope.resource_confirmation.status === 'CONFIRMED') {
    return 'RESOURCE_CONFIRMED'
  }
  return 'CONFIRMATION_PENDING'
}

export const selectRecommendedCase = (summaries: CaseSummary[]) => {
  if (summaries.length === 0) {
    throw new ApiError(
      '조회할 Case가 없습니다. 백엔드 데이터 준비 상태를 확인해주세요.',
      { status: 404, code: 'CASE_LIST_EMPTY' },
    )
  }

  const goldenCase = summaries.find(
    (item) => item.case_id === GOLDEN_CASE_ID && isActionableCase(item),
  )
  if (goldenCase) return goldenCase

  for (const status of recommendationOrder) {
    const candidate = summaries
      .filter((item) => item.workflow_status === status)
      .sort(compareCases)[0]
    if (candidate) return candidate
  }

  const completed = summaries
    .filter((item) => item.workflow_status === 'RECEIPT_CREATED')
    .sort(
      (left, right) =>
        new Date(right.updated_at).getTime() -
        new Date(left.updated_at).getTime(),
    )[0]
  return completed ?? [...summaries].sort(compareCases)[0]
}

export const createCaseActionKey = (
  caseId: string,
  action: IdempotentAction,
) => {
  const randomPart =
    typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `greenfab-${caseId}-${action}-${randomPart}`
}
