export interface ApiFieldError {
  field: string
  message: string
}

interface BackendErrorResponse {
  error?: {
    code?: unknown
    message?: unknown
    field_errors?: unknown
    trace_id?: unknown
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fieldErrors: ApiFieldError[]
  readonly traceId: string | null

  constructor({
    status,
    code,
    message,
    fieldErrors = [],
    traceId = null,
  }: {
    status: number
    code: string
    message: string
    fieldErrors?: ApiFieldError[]
    traceId?: string | null
  }) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
    this.traceId = traceId
  }
}

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
).replace(/\/$/, '')

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const parseFieldErrors = (value: unknown): ApiFieldError[] => {
  if (!Array.isArray(value)) return []

  return value.flatMap((item) => {
    if (!isRecord(item)) return []
    const field = typeof item.field === 'string' ? item.field : ''
    const message = typeof item.message === 'string' ? item.message : ''
    return message ? [{ field, message }] : []
  })
}

const readJson = async (response: Response): Promise<unknown> => {
  const text = await response.text()
  if (!text) return null

  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
}

export async function request<T>(
  path: string,
  { body, headers, ...init }: RequestOptions = {},
): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: '백엔드 서버에 연결할 수 없습니다.',
    })
  }

  const payload = await readJson(response)
  if (response.ok) return payload as T

  const backendPayload = isRecord(payload)
    ? (payload as BackendErrorResponse)
    : null
  const detail = backendPayload?.error
  const code = typeof detail?.code === 'string' ? detail.code : 'REQUEST_FAILED'
  const message =
    typeof detail?.message === 'string'
      ? detail.message
      : `요청을 처리하지 못했습니다. (HTTP ${response.status})`
  const traceId =
    typeof detail?.trace_id === 'string'
      ? detail.trace_id
      : response.headers.get('X-Trace-Id')

  throw new ApiError({
    status: response.status,
    code,
    message,
    fieldErrors: parseFieldErrors(detail?.field_errors),
    traceId,
  })
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
      (error.code === 'REQUEST_FAILED' ? '' : error.message) ||
      '서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해주세요.'
    )
  }

  return error.message || '요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.'
}

export const toApiError = (error: unknown): ApiError =>
  error instanceof ApiError
    ? error
    : new ApiError({
        status: 0,
        code: 'UNKNOWN_ERROR',
        message: '요청을 처리하지 못했습니다.',
      })

export const fieldMatches = (fieldPath: string, fieldName: string): boolean =>
  fieldPath === fieldName || fieldPath.endsWith(`.${fieldName}`)
