import { useEffect, useState } from 'react'
import { ApiError, toApiError, type ApiError as ApiErrorType } from './api/client'
import {
  GOLDEN_CASE_ID,
  confirmResource,
  createReceipt,
  getCase,
  getReceipt,
  resetDemo,
  runMatch,
  saveDecision,
  saveEsgScenario,
  saveResourcePassport,
} from './api/greenfabApi'
import { ApiErrorMessage } from './components/ApiErrorMessage'
import { ConfirmPage } from './pages/ConfirmPage'
import { DetectPage } from './pages/DetectPage'
import { MatchPage } from './pages/MatchPage'
import { OverviewPage } from './pages/OverviewPage'
import { PassportPage } from './pages/PassportPage'
import { ReceiptPage } from './pages/ReceiptPage'
import { ReviewPage } from './pages/ReviewPage'
import type {
  BackendEsgScenario,
  CaseEnvelope,
  DecisionDraft,
  EsgScenario,
  ResourcePassportDraft,
} from './types/loop'

type AppView =
  | 'overview'
  | 'detect'
  | 'confirm'
  | 'passport'
  | 'match'
  | 'review'
  | 'receipt'
  | 'verify'

interface InitialLocation {
  view: AppView
  receiptId: string | null
}

const CASE_SESSION_KEY = 'greenfab.activeCaseId'
const APP_VIEWS = new Set<AppView>([
  'overview',
  'detect',
  'confirm',
  'passport',
  'match',
  'review',
  'receipt',
])

const readInitialLocation = (): InitialLocation => {
  const route = window.location.hash.replace(/^#\/?/, '')
  const [view, encodedReceiptId] = route.split('/')
  if (view === 'verify' && encodedReceiptId) {
    return { view: 'verify', receiptId: decodeURIComponent(encodedReceiptId) }
  }
  if (APP_VIEWS.has(view as AppView)) {
    return { view: view as AppView, receiptId: null }
  }
  return { view: 'overview', receiptId: null }
}

const INITIAL_LOCATION = readInitialLocation()

const rememberCaseId = (caseId: string) => {
  try {
    window.sessionStorage.setItem(CASE_SESSION_KEY, caseId)
  } catch {
    // The URL hash still preserves the current view when storage is unavailable.
  }
}

const recalledCaseId = () => {
  try {
    return window.sessionStorage.getItem(CASE_SESSION_KEY) ?? GOLDEN_CASE_ID
  } catch {
    return GOLDEN_CASE_ID
  }
}

const toEsgScenario = (scenario: BackendEsgScenario | null): EsgScenario | null => {
  if (
    scenario?.source_type !== 'SCENARIO' ||
    scenario.formula_version !== 'ESG-SCENARIO-v0.1'
  ) {
    return null
  }
  return scenario as unknown as EsgScenario
}

function App() {
  const [view, setView] = useState<AppView>(INITIAL_LOCATION.view)
  const [caseEnvelope, setCaseEnvelope] = useState<CaseEnvelope | null>(null)
  const [isRestoring, setIsRestoring] = useState(
    INITIAL_LOCATION.view !== 'overview',
  )
  const [restoreError, setRestoreError] = useState<ApiErrorType | null>(null)

  const updateRoute = (nextView: AppView, receiptId?: string) => {
    const base = `${window.location.pathname}${window.location.search}`
    const hash =
      nextView === 'overview'
        ? ''
        : nextView === 'verify' && receiptId
          ? `#/verify/${encodeURIComponent(receiptId)}`
          : `#/${nextView}`
    window.history.replaceState(null, '', `${base}${hash}`)
  }

  const changeView = (nextView: Exclude<AppView, 'verify'>) => {
    window.scrollTo({ top: 0 })
    updateRoute(nextView)
    setView(nextView)
  }

  const restoreCurrentLocation = async () => {
    setIsRestoring(true)
    setRestoreError(null)
    try {
      const response =
        INITIAL_LOCATION.view === 'verify' && INITIAL_LOCATION.receiptId
          ? await getReceipt(INITIAL_LOCATION.receiptId)
          : await getCase(recalledCaseId())
      setCaseEnvelope(response)
      rememberCaseId(response.case.case_id)
    } catch (error) {
      setRestoreError(toApiError(error))
    } finally {
      setIsRestoring(false)
    }
  }

  useEffect(() => {
    if (INITIAL_LOCATION.view !== 'overview') {
      void restoreCurrentLocation()
    }
  }, [])

  const startDemo = async () => {
    const response = await resetDemo()
    setCaseEnvelope(response)
    rememberCaseId(response.case.case_id)
    changeView('detect')
  }

  if (view === 'overview') {
    return <OverviewPage onStartDemo={startDemo} />
  }

  if (!caseEnvelope) {
    return (
      <div className="app-shell">
        <main className="page-container" style={{ paddingBlock: '72px' }}>
          <span className="eyebrow">GREENFAB LOOP</span>
          <h1>{isRestoring ? '저장된 진행 상태를 불러오고 있습니다' : '진행 상태를 불러오지 못했습니다'}</h1>
          <p style={{ marginTop: '12px' }}>
            Backend에 저장된 Case 또는 Receipt를 다시 확인합니다.
          </p>
          <ApiErrorMessage error={restoreError} />
          {!isRestoring && (
            <div style={{ display: 'flex', gap: '8px', marginTop: '18px' }}>
              <button className="primary-button" type="button" onClick={restoreCurrentLocation}>
                다시 불러오기
              </button>
              <button className="secondary-button" type="button" onClick={() => changeView('overview')}>
                처음 화면으로
              </button>
            </div>
          )}
        </main>
      </div>
    )
  }

  const caseId = caseEnvelope.case.case_id
  const esgScenario = toEsgScenario(caseEnvelope.esg_scenario)
  const receipt = caseEnvelope.receipt

  const saveResourceConfirmation = async (
    status: 'CONFIRMED' | 'NOT_CONFIRMED',
  ) => {
    let response: CaseEnvelope

    try {
      response = await confirmResource(caseId, status)
    } catch (error) {
      const shouldRestartDemoCase =
        error instanceof ApiError &&
        error.status === 409 &&
        error.code === 'INVALID_STATE'

      if (!shouldRestartDemoCase) throw error

      const resetResponse = await resetDemo()
      setCaseEnvelope(resetResponse)
      rememberCaseId(resetResponse.case.case_id)
      response = await confirmResource(resetResponse.case.case_id, status)
    }

    setCaseEnvelope(response)
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
        onSelect={saveResourceConfirmation}
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
        onSave={async (draft: ResourcePassportDraft) => {
          const response = await saveResourcePassport(caseId, draft)
          setCaseEnvelope(response)
        }}
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
        onRunMatch={async () => {
          const response = await runMatch(caseId)
          setCaseEnvelope(response)
        }}
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
        onDecisionChange={async (draft: DecisionDraft) => {
          const response = await saveDecision(caseId, draft)
          setCaseEnvelope(response)
        }}
        onBack={() => changeView('match')}
        onGoToReceipt={() => changeView('receipt')}
      />
    )
  }

  const openVerifyReceipt = (receiptId: string) => {
    window.scrollTo({ top: 0 })
    updateRoute('verify', receiptId)
    setView('verify')
  }

  return (
    <ReceiptPage
      caseData={caseEnvelope.case}
      resourceConfirmation={caseEnvelope.resource_confirmation}
      resourcePassport={caseEnvelope.resource_passport}
      match={caseEnvelope.match}
      decision={caseEnvelope.decision}
      esgScenario={esgScenario}
      receipt={receipt}
      onEsgScenarioChange={async (scenario) => {
        const response = await saveEsgScenario(caseId, scenario)
        setCaseEnvelope(response)
      }}
      onCreateReceipt={async () => {
        const response = await createReceipt(caseId)
        setCaseEnvelope(response)
      }}
      onBackToReview={() => changeView('review')}
      onRestartDemo={startDemo}
      onVerifyReceipt={openVerifyReceipt}
      onExitVerify={() => changeView('receipt')}
      readOnly={view === 'verify'}
    />
  )
}

export default App
