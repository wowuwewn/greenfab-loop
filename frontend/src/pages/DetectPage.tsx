import { ArrowLeft, Info, RefreshCw } from 'lucide-react'
import { DetectFlow } from '../components/DetectFlow'
import { ModelEvidenceCard } from '../components/ModelEvidenceCard'
import { PriorityCaseCard } from '../components/PriorityCaseCard'
import { WorkflowStepper } from '../components/WorkflowStepper'
import {
  DETECT_ANALYSIS,
  VALIDATION_METRICS,
  WORKFLOW_STEPS,
} from '../data/detectData'
import type { DetectCase, ResourceConfirmation } from '../types/loop'

interface DetectPageProps {
  caseData: DetectCase
  onBackToOverview: () => void
  onGoToConfirm: () => void
  resourceConfirmation: ResourceConfirmation
}

export function DetectPage({
  caseData,
  onBackToOverview,
  onGoToConfirm,
  resourceConfirmation,
}: DetectPageProps) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="page-container topbar__inner">
          <a className="brand" href="#top" aria-label="GreenFab Loop 홈">
            <span className="brand__mark" aria-hidden="true">
              <RefreshCw size={17} strokeWidth={2} />
            </span>
            <span>GreenFab Loop</span>
          </a>
          <button
            className="overview-back-button"
            type="button"
            onClick={onBackToOverview}
          >
            <ArrowLeft size={16} strokeWidth={1.8} aria-hidden="true" />
            Overview로 돌아가기
          </button>
        </div>
      </header>

      <main className="page-container" id="top">
        <WorkflowStepper steps={WORKFLOW_STEPS} />

        <section className="hero-copy" aria-labelledby="page-title">
          <div className="hero-copy__main">
            <span className="eyebrow">01 · 위험 선별</span>
            <h1 id="page-title">먼저 볼 생산 건을 선별합니다</h1>
            <p>SECOM 분석 결과를 바탕으로 우선 확인할 생산 건을 보여줍니다.</p>
            <div className="provenance" aria-label="데이터 출처">
              <span className="provenance__badge">{caseData.source_type}</span>
              <span className="provenance__text">UCI SECOM + 모델 결과</span>
            </div>
          </div>
        </section>

        <DetectFlow
          analysis={DETECT_ANALYSIS}
          priorityCase={caseData}
          resourceConfirmation={resourceConfirmation}
        />

        <div className="content-grid">
          <ModelEvidenceCard
            analysis={DETECT_ANALYSIS}
            metrics={VALIDATION_METRICS}
          />
          <PriorityCaseCard
            analysis={DETECT_ANALYSIS}
            priorityCase={caseData}
            resourceConfirmation={resourceConfirmation}
            onGoToConfirm={onGoToConfirm}
          />
        </div>

        <aside className="interpretation-note" aria-label="위험 우선순위 해석 안내">
          <Info size={17} strokeWidth={1.9} aria-hidden="true" />
          <p>
            위험 우선순위는 불량 확률이 아니라 모델 점수를 기준으로 정렬한 검토
            순위입니다.
          </p>
        </aside>
      </main>
    </div>
  )
}
