import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_BASE_URL, api } from './client'
import { clearSessionApiKey, setSessionApiKey } from './sessionCredential'

const jsonResponse = (body: unknown, status = 200, traceId = 'trace-response') =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'X-Trace-Id': traceId,
    },
  })

afterEach(() => {
  clearSessionApiKey()
  vi.unstubAllGlobals()
})

describe('GreenFab API client', () => {
  it('loads the case list from the configured API root', async () => {
    const payload = [
      {
        case_id: 'SECOM-0116',
        risk_rank: 4,
        source_type: 'REAL',
        workflow_status: 'CONFIRMATION_PENDING',
        updated_at: '2026-08-18T00:00:00Z',
      },
    ]
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.listCases()).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/api/v1/cases?limit=100&offset=0`,
      expect.objectContaining({ headers: expect.any(Headers) }),
    )
  })

  it('sends case-scoped idempotency and actor headers for Match', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ case: {} }))
    vi.stubGlobal('fetch', fetchMock)

    await api.runMatch(
      'SECOM/0116',
      { top_k: 3 },
      'demo_operator',
      'greenfab-SECOM-0116-match-stable',
    )

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = options.headers as Headers
    expect(url).toBe(`${API_BASE_URL}/api/v1/cases/SECOM%2F0116/matches`)
    expect(options.method).toBe('POST')
    expect(options.body).toBe(JSON.stringify({ top_k: 3 }))
    expect(headers.get('X-Actor')).toBe('demo_operator')
    expect(headers.get('Idempotency-Key')).toBe(
      'greenfab-SECOM-0116-match-stable',
    )
  })

  it('sends a user-provided session key without a build-time secret', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)
    setSessionApiKey('runtime-session-access-key-123456')

    await api.listCases()

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = options.headers as Headers
    expect(headers.get('X-API-Key')).toBe('runtime-session-access-key-123456')
  })

  it('preserves validation fields and the response trace ID', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'VALIDATION_ERROR',
            message: '요청 필드를 확인해주세요.',
            field_errors: [
              {
                field: 'quantity',
                message: 'quantity and unit must be provided together',
              },
            ],
            trace_id: 'trace-body',
          },
        },
        422,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = api.savePassport(
      'SECOM-0116',
      {
        description: '반도체 세정 무기질 분말',
        quantity: 12,
        unit: null,
        condition: null,
        location: null,
        composition: null,
      },
      'demo_operator',
    )

    await expect(result).rejects.toMatchObject({
      status: 422,
      code: 'VALIDATION_ERROR',
      traceId: 'trace-body',
      fieldErrors: [
        {
          field: 'quantity',
          message: 'quantity and unit must be provided together',
        },
      ],
    })
  })

  it('keeps the header trace ID for non-JSON 503 responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('temporarily unavailable', {
          status: 503,
          headers: { 'X-Trace-Id': 'trace-503' },
        }),
      ),
    )

    await expect(api.listCases()).rejects.toMatchObject({
      status: 503,
      code: 'HTTP_ERROR',
      traceId: 'trace-503',
    })
  })

  it('maps fetch failures to a network error without inventing a trace ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    await expect(api.listCases()).rejects.toMatchObject({
      status: 0,
      code: 'NETWORK_ERROR',
      traceId: null,
    })
  })
})
