import { useState } from 'react'
import { DetectPage } from './pages/DetectPage'
import { ConfirmPage } from './pages/ConfirmPage'
import { OverviewPage } from './pages/OverviewPage'
import { PassportPage } from './pages/PassportPage'
import { RESOURCE_CONFIRMATION } from './data/detectData'
import type { ResourceConfirmation, ResourcePassport } from './types/loop'

type AppView = 'overview' | 'detect' | 'confirm' | 'passport'

function App() {
  const [view, setView] = useState<AppView>('overview')
  const [resourceConfirmation, setResourceConfirmation] =
    useState<ResourceConfirmation>({ ...RESOURCE_CONFIRMATION })
  const [resourcePassport, setResourcePassport] =
    useState<ResourcePassport | null>(null)

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
        onSave={setResourcePassport}
        onBackToConfirm={() => changeView('confirm')}
      />
    )
  }

  return (
    <OverviewPage
      onStartDemo={() => {
        setResourceConfirmation({ ...RESOURCE_CONFIRMATION })
        setResourcePassport(null)
        changeView('detect')
      }}
    />
  )
}

export default App
