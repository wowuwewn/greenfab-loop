import { useState } from 'react'
import { ArrowRight, RefreshCw } from 'lucide-react'
import { toApiError, type ApiError } from '../api/client'
import { ApiErrorMessage } from '../components/ApiErrorMessage'
import { CaseQueue } from '../components/CaseQueue'
import { DataLegend } from '../components/DataLegend'
import { ServiceFlowVisual } from '../components/ServiceFlowVisual'
import type { CaseSummary } from '../types/loop'
import '../overview.css'

interface OverviewPageProps {
  cases: CaseSummary[]
  recommendedCaseId: string | null
  selectedCaseId: string | null
  isCaseLoading: boolean
  onStartDemo: () => Promise<void>
  onOpenCase: (summary: CaseSummary) => Promise<void>
}

export function OverviewPage({
  cases,
  recommendedCaseId,
  selectedCaseId,
  isCaseLoading,
  onStartDemo,
  onOpenCase,
}: OverviewPageProps) {
  const [isStarting, setIsStarting] = useState(false)
  const [apiError, setApiError] = useState<ApiError | null>(null)

  const startDemo = async () => {
    setIsStarting(true)
    setApiError(null)

    try {
      await onStartDemo()
    } catch (error) {
      setApiError(toApiError(error))
    } finally {
      setIsStarting(false)
    }
  }

  return (
    <div className="app-shell overview-page">
      <header className="topbar">
        <div className="page-container topbar__inner">
          <a className="brand" href="#overview-top" aria-label="GreenFab Loop 홈">
            <span className="brand__mark" aria-hidden="true">
              <RefreshCw size={17} strokeWidth={2} />
            </span>
            <span>GreenFab Loop</span>
          </a>
        </div>
      </header>

      <main id="overview-top">
        <section className="overview-hero page-container" aria-labelledby="overview-title">
          <div className="overview-hero__copy">
            <span className="overview-eyebrow">GREENFAB LOOP</span>
            <h1 id="overview-title">
              <span>생산 위험 신호에서,</span>
              <span>다음 자원 경로까지.</span>
            </h1>
            <p className="overview-hero__subtitle">
              위험 생산 건을 먼저 선별하고 실제 자원 발생을 확인한 뒤,
              AI로 활용 후보를 찾고 규칙으로 조건을 확인한 후 사람이 최종 결정합니다.
            </p>
            <p className="overview-hero__support">
              결정 과정과 ESG 계산 근거는 Green Receipt로 남깁니다.
            </p>

            <div className="overview-hero__actions">
              <button
                className="overview-cta"
                type="button"
                onClick={startDemo}
                disabled={isStarting}
              >
                {isStarting ? '데모를 준비하고 있습니다...' : '데모 시작'}
                <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
              </button>
              <div className="demo-use-case" aria-label="이번 MVP 적용 사례">
                <span>이번 MVP 적용 사례 · 반도체 제조 · UCI SECOM</span>
              </div>
            </div>
            <ApiErrorMessage
              error={apiError}
              message={
                apiError?.status === 404 && apiError.code === 'NOT_FOUND'
                  ? '백엔드 데모 초기화 기능이 비활성화되어 있습니다.'
                  : undefined
              }
            />
          </div>

          <ServiceFlowVisual />
        </section>

        <div className="overview-operations page-container">
          <CaseQueue
            cases={cases}
            recommendedCaseId={recommendedCaseId}
            selectedCaseId={selectedCaseId}
            isLoading={isCaseLoading}
            onOpenCase={onOpenCase}
          />
        </div>

        <div className="overview-details page-container">
          <DataLegend />
        </div>
      </main>
    </div>
  )
}
