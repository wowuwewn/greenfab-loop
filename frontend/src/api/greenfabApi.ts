import { request } from './client'
import type {
  CaseEnvelope,
  DecisionDraft,
  EsgScenario,
  ResourceConfirmationStatus,
  ResourcePassportDraft,
} from '../types/loop'

export const GOLDEN_CASE_ID = 'SECOM-0116'

const casePath = (caseId: string) => `/cases/${encodeURIComponent(caseId)}`

const createIdempotencyKey = (prefix: 'match' | 'receipt') =>
  globalThis.crypto?.randomUUID?.() ??
  `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`

const receiptIdempotencyKeys = new Map<string, string>()

const receiptIdempotencyKey = (caseId: string) => {
  const existing = receiptIdempotencyKeys.get(caseId)
  if (existing) return existing
  const created = createIdempotencyKey('receipt')
  receiptIdempotencyKeys.set(caseId, created)
  return created
}

export const getCase = (caseId: string) =>
  request<CaseEnvelope>(casePath(caseId))

export const resetDemo = () =>
  request<CaseEnvelope>('/demo/reset', { method: 'POST' })

export const confirmResource = (
  caseId: string,
  status: Exclude<ResourceConfirmationStatus, 'PENDING'>,
) =>
  request<CaseEnvelope>(`${casePath(caseId)}/resource-confirmation`, {
    method: 'PUT',
    body: { status, confirmed_by: 'demo_operator' },
  })

export const saveResourcePassport = (
  caseId: string,
  draft: ResourcePassportDraft,
) =>
  request<CaseEnvelope>(`${casePath(caseId)}/resource-passport`, {
    method: 'PUT',
    body: draft,
  })

export const runMatch = (caseId: string) =>
  request<CaseEnvelope>(`${casePath(caseId)}/matches`, {
    method: 'POST',
    headers: { 'Idempotency-Key': createIdempotencyKey('match') },
    body: { top_k: 3 },
  })

export const saveDecision = (caseId: string, draft: DecisionDraft) =>
  request<CaseEnvelope>(`${casePath(caseId)}/decision`, {
    method: 'PUT',
    body: { ...draft, decided_by: 'demo_reviewer' },
  })


export const saveEsgScenario = (caseId: string, scenario: EsgScenario) =>
  request<CaseEnvelope>(`${casePath(caseId)}/esg-scenario`, {
    method: 'POST',
    body: { ...scenario.inputs, factor_source: scenario.factor_source },
  })

export const createReceipt = (caseId: string) =>
  request<CaseEnvelope>(`${casePath(caseId)}/receipt`, {
    method: 'POST',
    headers: { 'Idempotency-Key': receiptIdempotencyKey(caseId) },
  })

export const getReceipt = (receiptId: string) =>
  request<CaseEnvelope>(`/receipts/${encodeURIComponent(receiptId)}`)
