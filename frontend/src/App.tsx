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
  CaseSummary,
  DecisionDraft,
  ResourcePassportDraft,
} from './types/loop'
import {
  createCaseActionKey,
  deriveWorkflowStatus,
  getCaseWorkflowPresentation,
  selectRecommendedCase,
  type CaseDetailView,
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
  const [caseSummaries, setCaseSummaries] = useState<CaseSummary[]>([])
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [isCaseLoading, setIsCaseLoading] = useState(false)
  const [needsCredential, setNeedsCredential] = useState(false)
  const [isMutating, setIsMutating] = useState(false)
  const [requestError, setRequestError] = useState<ApiError | null>(null)
  const mutationInFlight = useRef(false)
  const idempotencyKeys = useRef(new Map<string, string>())

  const refreshCaseSummaries = useCallback(async () => {
    const summaries = await api.listCases()
    setCaseSummaries(summaries)
    return summaries
  }, [])

  const updateSummaryFromEnvelope = useCallback((detail: CaseEnvelope) => {
    setCaseSummaries((current) =>
      current.map((summary) =>
        summary.case_id === detail.case.case_id
          ? {
              ...summary,
              workflow_status: deriveWorkflowStatus(detail),
            }
          : summary,
      ),
    )
  }, [])

  const loadInitialData = useCallback(async () => {
    setIsInitialLoading(true)
    setRequestError(null)
    try {
      const summaries = await api.listCases()
      const recommendedCase = selectRecommendedCase(summaries)
      const detail = await api.getCase(recommendedCase.case_id)
      setCaseSummaries(summaries)
      setSelectedCaseId(recommendedCase.case_id)
      setCaseEnvelope(detail)
      setNeedsCredential(false)
    } catch (error) {
      const apiError = normalizeError(error)
      setRequestError(apiError)
      setNeedsCredential(
        apiError.code === 'AUTH_REQUIRED' || apiError.code === 'FORBIDDEN',
      )
      setCaseSummaries([])
      setSelectedCaseId(null)
      setCaseEnvelope(null)
    } finally {
      setIsInitialLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadInitialData()
  }, [loadInitialData])

  const changeView = useCallback((nextView: AppView) => {
    window.scrollTo({ top: 0 })
    setView(nextView)
  }, [])

  const openCase = useCallback(
    async (summary: CaseSummary, forcedView?: CaseDetailView) => {
      if (mutationInFlight.current) return

      setIsCaseLoading(true)
      setRequestError(null)
      try {
        const detail = await api.getCase(summary.case_id)
        const currentStatus = deriveWorkflowStatus(detail)
        setCaseEnvelope(detail)
        setSelectedCaseId(summary.case_id)
        updateSummaryFromEnvelope(detail)
        changeView(
          forcedView ??
            getCaseWorkflowPresentation(currentStatus).view,
        )
        setNeedsCredential(false)
      } catch (error) {
        const apiError = normalizeError(error)
        setRequestError(apiError)
        if (
          apiError.code === 'AUTH_REQUIRED' ||
          apiError.code === 'FORBIDDEN'
        ) {
          setNeedsCredential(true)
        }
        throw apiError
      } finally {
        setIsCaseLoading(false)
      }
    },
    [changeView, updateSummaryFromEnvelope],
  )

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

    const currentSummary = caseSummaries.find(
      (summary) => summary.case_id === caseEnvelope.case.case_id,
    )
    if (
      currentSummary &&
      getCaseWorkflowPresentation(currentSummary.workflow_status).readOnly
    ) {
      throw new ApiError('완료되거나 종료된 Case는 변경할 수 없습니다.', {
        status: 409,
        code: 'CASE_READ_ONLY',
      })
    }

    mutationInFlight.current = true
    setIsMutating(true)
    try {
      const updated = await operation(caseEnvelope)
      setCaseEnvelope(updated)
      setSelectedCaseId(updated.case.case_id)
      updateSummaryFromEnvelope(updated)

      try {
        await refreshCaseSummaries()
      } catch (refreshError) {
        // The mutation already succeeded. Keep the returned detail visible and
        // retry list synchronization on the next navigation or mutation.
        setRequestError(normalizeError(refreshError))
      }
    } catch (error) {
      const apiError = normalizeError(error)
      let displayError = apiError

      if (apiError.status === 409) {
        let refreshedDetail = false
        try {
          const refreshed = await api.getCase(caseEnvelope.case.case_id)
          setCaseEnvelope(refreshed)
          setSelectedCaseId(refreshed.case.case_id)
          updateSummaryFromEnvelope(refreshed)
          refreshedDetail = true
        } catch {
          // Preserve the original conflict and its trace ID when refresh fails.
        }

        try {
          await refreshCaseSummaries()
        } catch {
          // The refreshed detail still gives the operator the newest known state.
        }

        if (refreshedDetail) {
          displayError = new ApiError(
            `${apiError.message} 화면을 서버의 최신 Case 상태로 갱신했습니다.`,
            {
              status: apiError.status,
              code: apiError.code,
              fieldErrors: apiError.fieldErrors,
              traceId: apiError.traceId,
            },
          )
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
  const recommendedCase = selectRecommendedCase(caseSummaries)

  if (view === 'overview') {
    return (
      <OverviewPage
        cases={caseSummaries}
        recommendedCaseId={recommendedCase.case_id}
        selectedCaseId={selectedCaseId}
        isCaseLoading={isCaseLoading}
        onStartDemo={async () => {
          const presentation = getCaseWorkflowPresentation(
            recommendedCase.workflow_status,
          )
          await openCase(
            recommendedCase,
            presentation.readOnly ? presentation.view : 'detect',
          )
        }}
        onOpenCase={(summary) => openCase(summary)}
      />
    )
  }

  if (view === 'detect') {
    return (
      <DetectPage
        key={`detect:${caseId}`}
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
        key={`confirm:${caseId}`}
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
        onBackToOverview={() => changeView('overview')}
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
        key={`passport:${caseId}`}
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
        key={`match:${caseId}`}
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
        key={`review:${caseId}`}
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
      key={`receipt:${caseId}`}
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
