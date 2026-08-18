import { describe, expect, it } from 'vitest'
import type { CaseSummary } from './types/loop'
import {
  GOLDEN_CASE_ID,
  createCaseActionKey,
  selectGoldenCase,
} from './workflow'

const summary = (caseId: string): CaseSummary => ({
  case_id: caseId,
  risk_rank: 4,
  source_type: 'REAL',
  workflow_status: 'CONFIRMATION_PENDING',
  updated_at: '2026-08-18T00:00:00Z',
})

describe('Golden demo routing', () => {
  it('selects only SECOM-0116 even when another case appears first', () => {
    expect(
      selectGoldenCase([summary('SECOM-0001'), summary(GOLDEN_CASE_ID)]).case_id,
    ).toBe(GOLDEN_CASE_ID)
  })

  it('does not silently substitute a different case for Golden metrics', () => {
    expect(() => selectGoldenCase([summary('SECOM-0001')])).toThrowError(
      expect.objectContaining({ code: 'GOLDEN_CASE_NOT_FOUND' }),
    )
  })

  it('creates idempotency keys scoped by both case and action', () => {
    const matchKey = createCaseActionKey(GOLDEN_CASE_ID, 'match')
    const receiptKey = createCaseActionKey(GOLDEN_CASE_ID, 'receipt')

    expect(matchKey).toContain(`greenfab-${GOLDEN_CASE_ID}-match-`)
    expect(receiptKey).toContain(`greenfab-${GOLDEN_CASE_ID}-receipt-`)
    expect(matchKey).not.toBe(receiptKey)
  })
})
