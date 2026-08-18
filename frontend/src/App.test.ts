import { describe, expect, it } from 'vitest'
import type {
  CaseEnvelope,
  CaseSummary,
  WorkflowStatus,
} from './types/loop'
import {
  GOLDEN_CASE_ID,
  createCaseActionKey,
  deriveWorkflowStatus,
  getCaseWorkflowPresentation,
  selectRecommendedCase,
} from './workflow'

const summary = (
  caseId: string,
  workflowStatus: WorkflowStatus = 'CONFIRMATION_PENDING',
  riskRank = 4,
  updatedAt = '2026-08-18T00:00:00Z',
): CaseSummary => ({
  case_id: caseId,
  risk_rank: riskRank,
  source_type: 'DEMO',
  workflow_status: workflowStatus,
  updated_at: updatedAt,
})

const envelope = (overrides: Partial<CaseEnvelope> = {}): CaseEnvelope => ({
  case: {
    case_id: 'SECOM-0045',
    risk_rank: 1,
    shap_top_features: [],
    source_type: 'DEMO',
  },
  resource_confirmation: {
    status: 'PENDING',
    confirmed_by: null,
    confirmed_at: null,
    source_type: 'DEMO',
  },
  resource_passport: null,
  match: null,
  decision: null,
  esg_scenario: null,
  receipt: null,
  ...overrides,
})

describe('multi-Case workflow routing', () => {
  it('keeps an actionable SECOM-0116 as the recommended demo', () => {
    expect(
      selectRecommendedCase([
        summary('SECOM-0001', 'CONFIRMATION_PENDING', 1),
        summary(GOLDEN_CASE_ID),
      ]).case_id,
    ).toBe(GOLDEN_CASE_ID)
  })

  it('uses the highest-priority pending Case when Golden is closed', () => {
    expect(
      selectRecommendedCase([
        summary(GOLDEN_CASE_ID, 'CLOSED', 4),
        summary('SECOM-0100', 'PASSPORT_READY', 2),
        summary('SECOM-0045', 'CONFIRMATION_PENDING', 1),
      ]).case_id,
    ).toBe('SECOM-0045')
  })

  it('throws only when the Case list is empty', () => {
    expect(() => selectRecommendedCase([])).toThrowError(
      expect.objectContaining({ code: 'CASE_LIST_EMPTY' }),
    )
  })

  it('defines a view and next action for every server workflow status', () => {
    const statuses: WorkflowStatus[] = [
      'DETECTED',
      'CONFIRMATION_PENDING',
      'RESOURCE_CONFIRMED',
      'PASSPORT_READY',
      'MATCH_READY',
      'DECIDED',
      'SCENARIO_READY',
      'RECEIPT_CREATED',
      'NOT_CONFIRMED',
      'CLOSED',
    ]

    for (const status of statuses) {
      expect(getCaseWorkflowPresentation(status)).toMatchObject({
        label: expect.any(String),
        nextAction: expect.any(String),
        view: expect.any(String),
      })
    }
    expect(getCaseWorkflowPresentation('CLOSED').readOnly).toBe(true)
    expect(getCaseWorkflowPresentation('RECEIPT_CREATED').readOnly).toBe(true)
  })

  it('derives the queue status from the newest Case envelope state', () => {
    expect(deriveWorkflowStatus(envelope())).toBe('CONFIRMATION_PENDING')
    expect(
      deriveWorkflowStatus(
        envelope({
          resource_confirmation: {
            status: 'NOT_CONFIRMED',
            confirmed_by: 'field_operator',
            confirmed_at: '2026-08-18T01:00:00Z',
            source_type: 'DEMO',
          },
        }),
      ),
    ).toBe('CLOSED')
  })

  it('creates idempotency keys scoped by both Case and action', () => {
    const matchKey = createCaseActionKey(GOLDEN_CASE_ID, 'match')
    const receiptKey = createCaseActionKey(GOLDEN_CASE_ID, 'receipt')

    expect(matchKey).toContain(`greenfab-${GOLDEN_CASE_ID}-match-`)
    expect(receiptKey).toContain(`greenfab-${GOLDEN_CASE_ID}-receipt-`)
    expect(matchKey).not.toBe(receiptKey)
  })
})
