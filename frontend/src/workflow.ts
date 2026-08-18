import { ApiError } from './api/client'
import type { CaseSummary } from './types/loop'

export type IdempotentAction = 'match' | 'receipt'

export const GOLDEN_CASE_ID = 'SECOM-0116'

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

export const selectGoldenCase = (summaries: CaseSummary[]) => {
  if (summaries.length === 0) {
    throw new ApiError(
      '조회할 Case가 없습니다. 백엔드 데이터 준비 상태를 확인해주세요.',
      { status: 404, code: 'CASE_LIST_EMPTY' },
    )
  }

  const goldenCase = summaries.find((item) => item.case_id === GOLDEN_CASE_ID)
  if (!goldenCase) {
    throw new ApiError(
      '현재 화면의 UCI SECOM 지표와 일치하는 Golden Case(SECOM-0116)가 없습니다.',
      { status: 404, code: 'GOLDEN_CASE_NOT_FOUND' },
    )
  }
  return goldenCase
}
