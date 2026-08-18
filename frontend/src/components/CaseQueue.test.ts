import { describe, expect, it } from 'vitest'
import type { CaseSummary } from '../types/loop'
import { filterCaseSummaries } from './caseQueueFilters'

const cases: CaseSummary[] = Array.from({ length: 30 }, (_, index) => ({
  case_id: `SECOM-${String(index + 1).padStart(4, '0')}`,
  risk_rank: index + 1,
  source_type: 'DEMO',
  workflow_status:
    index === 3
      ? 'CLOSED'
      : index === 7
        ? 'RECEIPT_CREATED'
        : 'CONFIRMATION_PENDING',
  updated_at: '2026-08-18T00:00:00Z',
}))

describe('CaseQueue filtering', () => {
  it('keeps all 30 imported Case summaries with an empty search', () => {
    expect(filterCaseSummaries(cases, 'all', '')).toHaveLength(30)
  })

  it('searches Case IDs without case sensitivity', () => {
    expect(filterCaseSummaries(cases, 'all', 'secom-0004')).toEqual([
      cases[3],
    ])
  })

  it('separates actionable, complete, and closed workflows', () => {
    expect(filterCaseSummaries(cases, 'actionable', '')).toHaveLength(28)
    expect(filterCaseSummaries(cases, 'complete', '')).toEqual([cases[7]])
    expect(filterCaseSummaries(cases, 'closed', '')).toEqual([cases[3]])
  })
})
