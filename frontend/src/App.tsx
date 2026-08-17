import { useState } from 'react'
import { DetectPage } from './pages/DetectPage'
import { ConfirmPage } from './pages/ConfirmPage'
import { OverviewPage } from './pages/OverviewPage'
import { RESOURCE_CONFIRMATION } from './data/detectData'
import type { ResourceConfirmation } from './types/loop'

type AppView = 'overview' | 'detect' | 'confirm'

function App() {
  const [view, setView] = useState<AppView>('overview')
  const [resourceConfirmation, setResourceConfirmation] =
    useState<ResourceConfirmation>({ ...RESOURCE_CONFIRMATION })

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
          setResourceConfirmation({
            status,
            confirmed_by: 'demo_operator',
            confirmed_at: new Date().toISOString(),
            source_type: 'DEMO',
          })
        }}
        onReset={() => {
          setResourceConfirmation({ ...RESOURCE_CONFIRMATION })
        }}
        onBackToDetect={() => changeView('detect')}
      />
    )
  }

  return (
    <OverviewPage
      onStartDemo={() => {
        setResourceConfirmation({ ...RESOURCE_CONFIRMATION })
        changeView('detect')
      }}
    />
  )
}

export default App
