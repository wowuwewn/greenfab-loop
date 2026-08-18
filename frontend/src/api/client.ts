import type {
  ApiErrorBody,
  ApiFieldError,
  CaseEnvelope,
  CaseSummary,
  DecisionRequest,
  MatchRequest,
  ResourceConfirmationRequest,
  ResourcePassportRequest,
} from '../types/loop'
import { getSessionApiKey } from './sessionCredential'

export type { ApiFieldError } from '../types/loop'

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()

export const API_BASE_URL = (configuredBaseUrl || '').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fieldErrors: ApiFieldError[]
  readonly traceId: string | null

  constructor(
    message: string,
    options: {
      status: number
      code: string
      fieldErrors?: ApiFieldError[]
      traceId?: string | null
    },
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code
    this.fieldErrors = options.fieldErrors ?? []
    this.traceId = options.traceId ?? null
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  actor?: string
  idempotencyKey?: string
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const isErrorBody = (value: unknown): value is ApiErrorBody => {
  if (!isRecord(value) || !isRecord(value.error)) return false
  return (
    typeof value.error.code === 'string' &&
    typeof value.error.message === 'string'
  )
}

const parseFieldErrors = (value: unknown): ApiFieldError[] => {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!isRecord(item)) return []
    const field = typeof item.field === 'string' ? item.field : ''
    const message = typeof item.message === 'string' ? item.message : ''
    return message ? [{ field, message }] : []
  })
}

const readPayload = async (response: Response): Promise<unknown> => {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, actor, idempotencyKey, headers: requestHeaders, ...init } =
    options
  const headers = new Headers(requestHeaders)
  const apiKey = getSessionApiKey()
  headers.set('Accept', 'application/json')
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  if (apiKey) headers.set('X-API-Key', apiKey)
  if (actor) headers.set('X-Actor', actor)
  if (idempotencyKey) {
    headers.set('Idempotency-Key', idempotencyKey)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('백엔드 API에 연결할 수 없습니다.', {
      status: 0,
      code: 'NETWORK_ERROR',
      traceId: null,
    })
  }

  const traceId = response.headers.get('X-Trace-Id')
  const payload = await readPayload(response)

  if (!response.ok) {
    if (isErrorBody(payload)) {
      throw new ApiError(payload.error.message, {
        status: response.status,
        code: payload.error.code,
        fieldErrors: parseFieldErrors(payload.error.field_errors),
        traceId:
          typeof payload.error.trace_id === 'string' && payload.error.trace_id
            ? payload.error.trace_id
            : traceId,
      })
    }
    throw new ApiError(`API 요청이 실패했습니다. (${response.status})`, {
      status: response.status,
      code: 'HTTP_ERROR',
      traceId,
    })
  }

  return payload as T
}

const casePath = (caseId: string) =>
  `/api/v1/cases/${encodeURIComponent(caseId)}`

export const api = {
  listCases: (signal?: AbortSignal) =>
    request<CaseSummary[]>('/api/v1/cases', { signal }),
  getCase: (caseId: string, signal?: AbortSignal) =>
    request<CaseEnvelope>(casePath(caseId), { signal }),
  confirmResource: (caseId: string, payload: ResourceConfirmationRequest) =>
    request<CaseEnvelope>(`${casePath(caseId)}/resource-confirmation`, {
      method: 'PUT',
      body: payload,
    }),
  savePassport: (
    caseId: string,
    payload: ResourcePassportRequest,
    actor: string,
  ) =>
    request<CaseEnvelope>(`${casePath(caseId)}/resource-passport`, {
      method: 'PUT',
      body: payload,
      actor,
    }),
  runMatch: (
    caseId: string,
    payload: MatchRequest,
    actor: string,
    idempotencyKey: string,
  ) =>
    request<CaseEnvelope>(`${casePath(caseId)}/matches`, {
      method: 'POST',
      body: payload,
      actor,
      idempotencyKey,
    }),
  saveDecision: (caseId: string, payload: DecisionRequest) =>
    request<CaseEnvelope>(`${casePath(caseId)}/decision`, {
      method: 'PUT',
      body: payload,
    }),
  createEsgScenario: (caseId: string, actor: string) =>
    request<CaseEnvelope>(`${casePath(caseId)}/esg-scenario`, {
      method: 'POST',
      actor,
    }),
  createReceipt: (caseId: string, actor: string, idempotencyKey: string) =>
    request<CaseEnvelope>(`${casePath(caseId)}/receipt`, {
      method: 'POST',
      actor,
      idempotencyKey,
    }),
  getReceipt: (caseId: string) =>
    request<CaseEnvelope>(`${casePath(caseId)}/receipt`),
  resetDemo: () =>
    request<CaseEnvelope>('/api/v1/demo/reset', { method: 'POST' }),
}

const conflictMessages: Record<string, string> = {
  INVALID_STATE:
    '현재 단계에서는 이 작업을 진행할 수 없습니다. 이전 단계를 다시 확인해주세요.',
  INVALID_CANDIDATE:
    '현재 Match 결과에 없는 후보입니다. 후보 탐색을 다시 실행해주세요.',
  CANDIDATE_NOT_REVIEWABLE: '검토 가능 상태의 후보만 승인할 수 있습니다.',
  MATCH_IN_PROGRESS:
    '후보 탐색이 이미 진행 중입니다. 잠시 후 다시 확인해주세요.',
  PASSPORT_CHANGED_DURING_MATCH:
    '후보 탐색 중 자원 정보가 변경되었습니다. 최신 정보로 후보 탐색을 다시 실행해주세요.',
  DEMAND_CHANGED_DURING_MATCH:
    '후보 정보가 변경되었습니다. 최신 수요 정보로 후보 탐색을 다시 실행해주세요.',
  DEMAND_CHANGED_SINCE_MATCH:
    '후보 정보가 변경되었습니다. 최신 수요 정보로 후보 탐색을 다시 실행해주세요.',
  CASE_CHANGED_DURING_MATCH:
    '후보 탐색 중 Case 상태가 변경되었습니다. 현재 상태를 다시 불러온 후 재시도해주세요.',
}

const unavailableMessages: Record<string, string> = {
  MATCH_UNAVAILABLE:
    '현재 AI 후보 탐색 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해주세요.',
  DEMAND_INDEX_UNAVAILABLE:
    '수요 검색 인덱스를 갱신하지 못했습니다. 잠시 후 다시 시도해주세요.',
  DATABASE_UNAVAILABLE:
    '서버 데이터 연결에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.',
}

export const getApiErrorMessage = (error: ApiError): string => {
  if (error.status === 0) {
    return '백엔드 서버에 연결할 수 없습니다. 서버 상태를 확인한 후 다시 시도해주세요.'
  }
  if (error.status === 409 && conflictMessages[error.code]) {
    return conflictMessages[error.code]
  }
  if (error.status === 422) {
    return error.message || '입력값을 다시 확인해주세요.'
  }
  if (error.status === 503) {
    return (
      unavailableMessages[error.code] ||
      (error.code === 'HTTP_ERROR' ? '' : error.message) ||
      '서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해주세요.'
    )
  }
  return error.message || '요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.'
}

export const toApiError = (error: unknown): ApiError =>
  error instanceof ApiError
    ? error
    : new ApiError('요청을 처리하지 못했습니다.', {
        status: 0,
        code: 'UNKNOWN_ERROR',
      })

export const fieldMatches = (fieldPath: string, fieldName: string): boolean =>
  fieldPath === fieldName || fieldPath.endsWith(`.${fieldName}`)
