import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from './api/client'
import { setSessionApiKey } from './api/sessionCredential'
import {
  ApiBlockingState,
  ApiCredentialGate,
} from './components/ApiFeedback'
import { ConfirmPage } from './pages/ConfirmPage'
import { DetectPage } from './pages/DetectPage'
import { MatchPage } from './pages/MatchPage'
import { OverviewPage } from './pages/OverviewPage'
import { PassportPage } from './pages/PassportPage'
import { ReceiptPage } from './pages/ReceiptPage'
import { ReviewPage } from './pages/ReviewPage'
import type {
  CaseEnvelope,
  DecisionDraft,
  ResourcePassportDraft,
} from './types/loop'
import {
  createCaseActionKey,
  selectGoldenCase,
  type IdempotentAction,
} from './workflow'

type AppView =
  | 'overview'
  | 'detect'
  | 'confirm'
  | 'passport'
  | 'match'
  | 'review'
  | 'receipt'

const OPERATOR = 'demo_operator'
const REVIEWER = 'demo_reviewer'

const normalizeError = (error: unknown) =>
  error instanceof ApiError
    ? error
    : new ApiError('예상하지 못한 오류가 발생했습니다.', {
        status: 0,
        code: 'UNKNOWN_ERROR',
      })

const keyScope = (caseId: string, action: IdempotentAction) =>
  `${caseId}:${action}`

function App() {
  const [view, setView] = useState<AppView>('overview')
  const [caseEnvelope, setCaseEnvelope] = useState<CaseEnvelope | null>(null)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [needsCredential, setNeedsCredential] = useState(false)
  const [isMutating, setIsMutating] = useState(false)
  const [requestError, setRequestError] = useState<ApiError | null>(null)
  const mutationInFlight = useRef(false)
  const idempotencyKeys = useRef(new Map<string, string>())

  const loadInitialData = useCallback(async () => {
    setIsInitialLoading(true)
    setRequestError(null)
    try {
      const summaries = await api.listCases()
      const goldenCase = selectGoldenCase(summaries)
      const detail = await api.getCase(goldenCase.case_id)
      setCaseEnvelope(detail)
      setNeedsCredential(false)
    } catch (error) {
      const apiError = normalizeError(error)
      setRequestError(apiError)
      setNeedsCredential(
        apiError.code === 'AUTH_REQUIRED' || apiError.code === 'FORBIDDEN',
      )
      setCaseEnvelope(null)
    } finally {
      setIsInitialLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadInitialData()
  }, [loadInitialData])

  const changeView = (nextView: AppView) => {
    window.scrollTo({ top: 0 })
    setView(nextView)
  }

  const getStableKey = (caseId: string, action: IdempotentAction) => {
    const scope = keyScope(caseId, action)
    const existing = idempotencyKeys.current.get(scope)
    if (existing) return existing
    const next = createCaseActionKey(caseId, action)
    idempotencyKeys.current.set(scope, next)
    return next
  }

  const clearStableKey = (caseId: string, action: IdempotentAction) => {
    idempotencyKeys.current.delete(keyScope(caseId, action))
  }

  const mutate = async (
    operation: (current: CaseEnvelope) => Promise<CaseEnvelope>,
  ): Promise<void> => {
    if (!caseEnvelope || mutationInFlight.current) return
    mutationInFlight.current = true
    setIsMutating(true)
    try {
      setCaseEnvelope(await operation(caseEnvelope))
    } catch (error) {
      const apiError = normalizeError(error)
      let displayError = apiError

      if (apiError.status === 409) {
        try {
          const refreshed = await api.getCase(caseEnvelope.case.case_id)
          setCaseEnvelope(refreshed)
          displayError = new ApiError(
            `${apiError.message} 화면을 서버의 최신 Case 상태로 갱신했습니다.`,
            {
              status: apiError.status,
              code: apiError.code,
              fieldErrors: apiError.fieldErrors,
              traceId: apiError.traceId,
            },
          )
        } catch {
          // Preserve the original conflict and its trace ID when refresh fails.
        }
      }

      if (apiError.code === 'AUTH_REQUIRED' || apiError.code === 'FORBIDDEN') {
        setRequestError(apiError)
        setNeedsCredential(true)
      }
      throw displayError
    } finally {
      mutationInFlight.current = false
      setIsMutating(false)
    }
  }

  if (needsCredential) {
    return (
      <ApiCredentialGate
        error={requestError}
        isConnecting={isInitialLoading}
        onConnect={(apiKey) => {
          setSessionApiKey(apiKey)
          void loadInitialData()
        }}
      />
    )
  }

  if (isInitialLoading || !caseEnvelope) {
    return (
      <ApiBlockingState
        error={isInitialLoading ? null : requestError}
        onRetry={() => void loadInitialData()}
      />
    )
  }

  const caseId = caseEnvelope.case.case_id

  if (view === 'overview') {
    return (
      <OverviewPage
        onStartDemo={async () => {
          changeView('detect')
        }}
      />
    )
  }

  if (view === 'detect') {
    return (
      <DetectPage
        caseData={caseEnvelope.case}
        resourceConfirmation={caseEnvelope.resource_confirmation}
        onBackToOverview={() => changeView('overview')}
        onGoToConfirm={() => changeView('confirm')}
      />
    )
  }

  if (view === 'confirm') {
    return (
      <ConfirmPage
        caseData={caseEnvelope.case}
        resourceConfirmation={caseEnvelope.resource_confirmation}
        onSelect={(status) =>
          mutate(() =>
            api.confirmResource(caseId, {
              status,
              confirmed_by: OPERATOR,
            }),
          )
        }
        onBackToDetect={() => changeView('detect')}
        onGoToPassport={() => {
          if (caseEnvelope.resource_confirmation.status === 'CONFIRMED') {
            changeView('passport')
          }
        }}
      />
    )
  }

  if (view === 'passport') {
    return (
      <PassportPage
        caseData={caseEnvelope.case}
        resourceConfirmation={caseEnvelope.resource_confirmation}
        resourcePassport={caseEnvelope.resource_passport}
        onSave={(passport: ResourcePassportDraft) =>
          mutate(async () => {
            const result = await api.savePassport(caseId, passport, OPERATOR)
            clearStableKey(caseId, 'match')
            clearStableKey(caseId, 'receipt')
            return result
          })
        }
        onBackToConfirm={() => changeView('confirm')}
        onGoToMatch={() => changeView('match')}
      />
    )
  }

  if (view === 'match') {
    return (
      <MatchPage
        resourcePassport={caseEnvelope.resource_passport}
        match={caseEnvelope.match}
        onRunMatch={() =>
          mutate(() =>
            api.runMatch(
              caseId,
              { top_k: 3 },
              OPERATOR,
              getStableKey(caseId, 'match'),
            ),
          )
        }
        onBackToPassport={() => changeView('passport')}
        onGoToReview={() => changeView('review')}
      />
    )
  }

  if (view === 'review') {
    return (
      <ReviewPage
        match={caseEnvelope.match}
        decision={caseEnvelope.decision}
        onDecisionChange={(decision: DecisionDraft) =>
          mutate(async () => {
            const result = await api.saveDecision(caseId, {
              ...decision,
              decided_by: REVIEWER,
            })
            clearStableKey(caseId, 'receipt')
            return result
          })
        }
        onBack={() => changeView('match')}
        onGoToReceipt={() => changeView('receipt')}
      />
    )
  }

  return (
    <ReceiptPage
      caseData={caseEnvelope.case}
      resourceConfirmation={caseEnvelope.resource_confirmation}
      resourcePassport={caseEnvelope.resource_passport}
      match={caseEnvelope.match}
      decision={caseEnvelope.decision}
      esgScenario={caseEnvelope.esg_scenario}
      receipt={caseEnvelope.receipt}
      isBusy={isMutating}
      onGenerateEsgScenario={() =>
        mutate(() => api.createEsgScenario(caseId, OPERATOR))
      }
      onCreateReceipt={() =>
        mutate(async () => {
          await api.createReceipt(
            caseId,
            OPERATOR,
            getStableKey(caseId, 'receipt'),
          )
          return api.getReceipt(caseId)
        })
      }
      onBackToReview={() => changeView('review')}
    />
  )
}

export default App
