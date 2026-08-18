import { request } from './client'
import type {
  CaseEnvelope,
  DecisionDraft,
  ResourceConfirmationStatus,
  ResourcePassportDraft,
} from '../types/loop'

export const GOLDEN_CASE_ID = 'SECOM-0116'

const casePath = (caseId: string) => `/cases/${encodeURIComponent(caseId)}`

const createIdempotencyKey = () =>
  globalThis.crypto?.randomUUID?.() ??
  `match-${Date.now()}-${Math.random().toString(16).slice(2)}`

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
    headers: { 'Idempotency-Key': createIdempotencyKey() },
    body: { top_k: 3 },
  })

export const saveDecision = (caseId: string, draft: DecisionDraft) =>
  request<CaseEnvelope>(`${casePath(caseId)}/decision`, {
    method: 'PUT',
    body: { ...draft, decided_by: 'demo_reviewer' },
  })
