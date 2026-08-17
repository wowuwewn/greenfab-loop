import {
  ArrowRight,
  Database,
  ScanLine,
  Target,
  UserCheck,
  type LucideIcon,
} from 'lucide-react'
import type {
  DetectAnalysis,
  DetectCase,
  ResourceConfirmation,
} from '../types/loop'

interface DetectFlowProps {
  analysis: DetectAnalysis
  priorityCase: DetectCase
  resourceConfirmation: ResourceConfirmation
}

interface FlowNode {
  title: string
  detail: string
  icon: LucideIcon
  tone: 'source' | 'model' | 'priority' | 'next'
}

const formatNumber = new Intl.NumberFormat('ko-KR')

export function DetectFlow({
  analysis,
  priorityCase,
  resourceConfirmation,
}: DetectFlowProps) {
  const nodes: FlowNode[] = [
    {
      title: analysis.dataset_name,
      detail: `${formatNumber.format(analysis.total_cases)}건`,
      icon: Database,
      tone: 'source',
    },
    {
      title: analysis.model_name,
      detail: '모델 점수 기반 우선순위',
      icon: ScanLine,
      tone: 'model',
    },
    {
      title: priorityCase.case_id,
      detail: `검토 우선순위 ${priorityCase.risk_rank}위`,
      icon: Target,
      tone: 'priority',
    },
    {
      title: '현장 확인',
      detail:
        resourceConfirmation.status === 'PENDING'
          ? '실제 자원 발생 여부 확인'
          : '확인 결과 기록',
      icon: UserCheck,
      tone: 'next',
    },
  ]

  return (
    <section className="flow-section" aria-labelledby="flow-title">
      <div className="flow-section__heading">
        <h2 id="flow-title">선별 과정</h2>
        <p>실제 데이터에서 담당자의 확인까지 이어집니다.</p>
      </div>

      <ol className="detect-flow">
        {nodes.map((node, index) => {
          const Icon = node.icon
          return (
            <li className="detect-flow__item" key={node.title}>
              <div className={`flow-step flow-step--${node.tone}`}>
                <div className="flow-step__icon" aria-hidden="true">
                  <Icon size={20} strokeWidth={1.8} />
                </div>
                <div className="flow-step__copy">
                  <strong>{node.title}</strong>
                  <span>{node.detail}</span>
                </div>
              </div>
              {index < nodes.length - 1 && (
                <div className="flow-connector" aria-hidden="true">
                  <span />
                  <ArrowRight size={16} strokeWidth={1.6} />
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
