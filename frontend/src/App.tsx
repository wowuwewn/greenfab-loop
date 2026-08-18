import { useState } from 'react'
import { DetectPage } from './pages/DetectPage'
import { ConfirmPage } from './pages/ConfirmPage'
import { OverviewPage } from './pages/OverviewPage'
import { PassportPage } from './pages/PassportPage'
import { ReviewPage } from './pages/ReviewPage'
import { ReceiptPage } from './pages/ReceiptPage'
import { PRIORITY_CASE, RESOURCE_CONFIRMATION } from './data/detectData'
import type {
  Decision,
  EsgScenario,
  Match,
  Receipt,
  ResourceConfirmation,
  ResourcePassport,
} from './types/loop'

type AppView =
  | 'overview'
  | 'detect'
  | 'confirm'
  | 'passport'
  | 'review'
  | 'receipt'

function App() {
  const [view, setView] = useState<AppView>('overview')
  const [resourceConfirmation, setResourceConfirmation] =
    useState<ResourceConfirmation>({ ...RESOURCE_CONFIRMATION })
  const [resourcePassport, setResourcePassport] =
    useState<ResourcePassport | null>(null)
  const [match, setMatch] = useState<Match | null>(null)
  const [decision, setDecision] = useState<Decision | null>(null)
  const [esgScenario, setEsgScenario] = useState<EsgScenario | null>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null)

  const changeView = (nextView: AppView) => {
    window.scrollTo({ top: 0 })
    setView(nextView)
  }

  if (view === 'detect') {
    return (
      <DetectPage
        resourceConfirmation={resourceConfirmation}
        onBackToOverview={() => changeView('overview')}
        onGoToConfirm={() => changeView('confirm')}
      />
    )
  }

  if (view === 'confirm') {
    return (
      <ConfirmPage
        resourceConfirmation={resourceConfirmation}
        onSelect={(status) => {
          setResourcePassport(null)
          setResourceConfirmation({
            status,
            confirmed_by: 'demo_operator',
            confirmed_at: new Date().toISOString(),
            source_type: 'DEMO',
          })
        }}
        onReset={() => {
          setResourcePassport(null)
          setResourceConfirmation({ ...RESOURCE_CONFIRMATION })
        }}
        onBackToDetect={() => changeView('detect')}
        onGoToPassport={() => {
          if (resourceConfirmation.status === 'CONFIRMED') {
            changeView('passport')
          }
        }}
      />
    )
  }

  if (view === 'passport') {
    return (
      <PassportPage
        resourceConfirmation={resourceConfirmation}
        resourcePassport={resourcePassport}
        onSave={(passport) => {
          setResourcePassport(passport)
          setMatch(null)
          setDecision(null)
          setEsgScenario(null)
          setReceipt(null)
        }}
        onBackToConfirm={() => changeView('confirm')}
        onGoToReview={() => changeView('review')}
      />
    )
  }

  if (view === 'review') {
    return (
      <ReviewPage
        match={match}
        decision={decision}
        onDecisionChange={(nextDecision) => {
          setDecision(nextDecision)
          setReceipt(null)
        }}
        onBack={() => changeView('passport')}
        onGoToReceipt={() => changeView('receipt')}
      />
    )
  }

  if (view === 'receipt') {
    return (
      <ReceiptPage
        caseData={PRIORITY_CASE}
        resourceConfirmation={resourceConfirmation}
        resourcePassport={resourcePassport}
        match={match}
        decision={decision}
        esgScenario={esgScenario}
        receipt={receipt}
        onCreateReceipt={() => {
          if (!resourcePassport || !decision) return

          setReceipt({
            receipt_id: `RECEIPT-${PRIORITY_CASE.case_id}`,
            case_id: PRIORITY_CASE.case_id,
            passport_id: resourcePassport.passport_id,
            selected_demand_id: decision.selected_demand_id,
            decision_status: decision.status,
            handoff_status:
              decision.status === 'APPROVED'
                ? 'APPROVED'
                : 'RESOURCE_CONFIRMED',
            created_at: new Date().toISOString(),
          })
        }}
        onBackToReview={() => changeView('review')}
      />
    )
  }

  return (
    <OverviewPage
      onStartDemo={() => {
        setResourceConfirmation({ ...RESOURCE_CONFIRMATION })
        setResourcePassport(null)
        setMatch(null)
        setDecision(null)
        setEsgScenario(null)
        setReceipt(null)
        changeView('detect')
      }}
    />
  )
}

export default App
