import { useId, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { DetectAnalysis, ValidationMetrics } from '../types/loop'

interface ModelEvidenceCardProps {
  analysis: DetectAnalysis
  metrics: ValidationMetrics
}

const formatNumber = new Intl.NumberFormat('ko-KR')
const formatPercent = (value: number) => `${value.toFixed(2)}%`

export function ModelEvidenceCard({
  analysis,
  metrics,
}: ModelEvidenceCardProps) {
  const [isOpen, setIsOpen] = useState(false)
  const detailsId = useId()

  const evidenceRows = [
    ['분석 대상', `${formatNumber.format(analysis.total_cases)}건`],
    ['실제 불량', `${formatNumber.format(analysis.defect_cases)}건`],
    [
      'Top 20% 검토 시 실제 불량',
      `${formatNumber.format(analysis.captured_defects_top_20)}건`,
    ],
    ['Top 20% 포착률', formatPercent(analysis.capture_rate_top_20)],
  ]

  const metricRows = [
    ['Recall', metrics.recall],
    ['Precision', metrics.precision],
    ['F1', metrics.f1],
    ['Balanced Acc.', metrics.balanced_accuracy],
  ]

  return (
    <section className="evidence-card" aria-labelledby="evidence-title">
      <div className="card-heading">
        <div>
          <h2 id="evidence-title">분석 근거</h2>
          <p>
            {analysis.dataset_name} <span aria-hidden="true">·</span>{' '}
            {analysis.model_name}
          </p>
          <span className="evidence-context">과거 데이터 OOF 검증 결과</span>
        </div>
      </div>

      <dl className="evidence-list">
        {evidenceRows.map(([label, value], index) => (
          <div className="evidence-row" key={label}>
            <dt>{label}</dt>
            <dd className={index === evidenceRows.length - 1 ? 'is-accent' : ''}>
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <button
        className="secondary-button"
        type="button"
        aria-expanded={isOpen}
        aria-controls={detailsId}
        onClick={() => setIsOpen((current) => !current)}
      >
        모델 검증 상세 보기
        <ChevronDown
          className={isOpen ? 'is-rotated' : ''}
          size={17}
          strokeWidth={1.8}
          aria-hidden="true"
        />
      </button>

      <div
        className={`validation-details${isOpen ? ' is-open' : ''}`}
        id={detailsId}
        aria-hidden={!isOpen}
      >
        <div className="validation-details__inner">
          <p>실제 검증 지표</p>
          <dl>
            {metricRows.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{formatPercent(Number(value))}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  )
}
