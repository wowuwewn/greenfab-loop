import { useState } from 'react'
import {
  confirmResource,
  resetDemo,
  runMatch,
  saveDecision,
  saveResourcePassport,
} from './api/greenfabApi'
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
  EsgScenario,
  Receipt,
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

function App() {
  const [view, setView] = useState<AppView>('overview')
  const [caseEnvelope, setCaseEnvelope] = useState<CaseEnvelope | null>(null)
  const [esgScenario, setEsgScenario] = useState<EsgScenario | null>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null)

  const changeView = (nextView: AppView) => {
    window.scrollTo({ top: 0 })
    setView(nextView)
  }

  const startDemo = async () => {
    const response = await resetDemo()
    setCaseEnvelope(response)
    setEsgScenario(null)
    setReceipt(null)
    changeView('detect')
  }

  if (view === 'overview' || !caseEnvelope) {
    return <OverviewPage onStartDemo={startDemo} />
  }

  const caseId = caseEnvelope.case.case_id

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
        onSelect={async (status) => {
          const response = await confirmResource(caseId, status)
          setCaseEnvelope(response)
          setEsgScenario(null)
          setReceipt(null)
        }}
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
          setEsgScenario(null)
          setReceipt(null)
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
          setEsgScenario(null)
          setReceipt(null)
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
          setReceipt(null)
        }}
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
      esgScenario={esgScenario}
      receipt={receipt}
      onEsgScenarioChange={setEsgScenario}
      onCreateReceipt={() => {
        const resourcePassport = caseEnvelope.resource_passport
        const decision = caseEnvelope.decision
        if (!resourcePassport || !decision || !esgScenario) return

        setReceipt({
          receipt_id: `RECEIPT-${caseEnvelope.case.case_id}`,
          case_id: caseEnvelope.case.case_id,
          passport_id: resourcePassport.passport_id,
          selected_demand_id: decision.selected_demand_id,
          decision_status: decision.status,
          handoff_status:
            decision.status === 'APPROVED' ? 'APPROVED' : 'RESOURCE_CONFIRMED',
          created_at: new Date().toISOString(),
        })
      }}
      onBackToReview={() => changeView('review')}
    />
  )
}

export default App
