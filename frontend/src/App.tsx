import { useState } from 'react'
import { DetectPage } from './pages/DetectPage'
import { OverviewPage } from './pages/OverviewPage'

type AppView = 'overview' | 'detect'

function App() {
  const [view, setView] = useState<AppView>('overview')

  if (view === 'detect') {
    return (
      <DetectPage
        onBackToOverview={() => {
          window.scrollTo({ top: 0 })
          setView('overview')
        }}
      />
    )
  }

  return (
    <OverviewPage
      onStartDemo={() => {
        window.scrollTo({ top: 0 })
        setView('detect')
      }}
    />
  )
}

export default App
