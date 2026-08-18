import { ArrowRight } from 'lucide-react'
import type {
  DetectAnalysis,
  DetectCase,
  ResourceConfirmation,
} from '../types/loop'

interface PriorityCaseCardProps {
  analysis: DetectAnalysis
  priorityCase: DetectCase
  resourceConfirmation: ResourceConfirmation
  onGoToConfirm: () => void
}

const formatNumber = new Intl.NumberFormat('ko-KR')
const formatShapValue = (value: number) =>
  `${value >= 0 ? '+' : ''}${value.toFixed(3)}`

export function PriorityCaseCard({
  analysis,
  priorityCase,
  resourceConfirmation,
  onGoToConfirm,
}: PriorityCaseCardProps) {
  const confirmationPresentation = {
    PENDING: {
      currentStatus: '실제 자원 발생 여부 확인 전',
      nextStep: '담당자가 실제 자원 발생 여부를 확인합니다.',
      buttonLabel: '확인 단계로 이동',
    },
    CONFIRMED: {
      currentStatus: '실제 자원 발생 확인 완료',
      nextStep: '확인된 자원 정보를 Passport에 정리합니다.',
      buttonLabel: '현장 확인 결과 보기',
    },
    NOT_CONFIRMED: {
      currentStatus: '자원 미발생 확인 · 검토 종료',
      nextStep: '종료된 Case이며 확인 결과를 조회할 수 있습니다.',
      buttonLabel: '종료 결과 보기',
    },
  }[resourceConfirmation.status]

  return (
    <section className="priority-card" aria-labelledby="priority-title">
      <div className="priority-card__topline">
        <span>우선 검토 Case</span>
      </div>

      <h2 id="priority-title">{priorityCase.case_id}</h2>

      <div className="priority-rank">
        <span>검토 우선순위</span>
        <strong>
          {priorityCase.risk_rank}위
          <small> / {formatNumber.format(analysis.total_cases)}건</small>
        </strong>
      </div>

      {priorityCase.shap_top_features &&
        priorityCase.shap_top_features.length > 0 && (
          <div className="priority-shap">
            <div className="priority-shap__heading">
              <span>예측에 영향을 준 변수</span>
              <small>{priorityCase.source_type} · SHAP</small>
            </div>
            <dl>
              {priorityCase.shap_top_features.map((feature) => (
                <div key={feature.feature_name}>
                  <dt>{feature.feature_name}</dt>
                  <dd>{formatShapValue(feature.shap_value)}</dd>
                </div>
              ))}
            </dl>
            <p>
              모델 예측에 대한 기여도이며, 실제 공정 원인이나 인과관계를
              의미하지 않습니다.
            </p>
          </div>
        )}

      <div className="action-details">
        <div>
          <span>현재 상태</span>
          <p>{confirmationPresentation.currentStatus}</p>
        </div>
        <div>
          <span>다음 단계</span>
          <p>{confirmationPresentation.nextStep}</p>
        </div>
      </div>

      <button
        className="primary-button"
        type="button"
        onClick={onGoToConfirm}
      >
        {confirmationPresentation.buttonLabel}
        <ArrowRight size={18} strokeWidth={1.9} aria-hidden="true" />
      </button>
    </section>
  )
}
