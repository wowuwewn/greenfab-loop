import { Check } from 'lucide-react'
import type { WorkflowStep } from '../types/loop'

interface WorkflowStepperProps {
  steps: WorkflowStep[]
  activeStep?: number
}

export function WorkflowStepper({
  steps,
  activeStep = 0,
}: WorkflowStepperProps) {
  return (
    <nav className="workflow" aria-label="GreenFab Loop 진행 단계">
      <ol className="workflow__list">
        {steps.map((step, index) => {
          const isActive = index === activeStep
          const isComplete = index < activeStep

          return (
            <li
              className={`workflow__step${isActive ? ' is-active' : ''}${isComplete ? ' is-complete' : ''}`}
              key={step.id}
              aria-current={isActive ? 'step' : undefined}
            >
              <span className="workflow__marker" aria-hidden="true">
                {isComplete ? <Check size={12} strokeWidth={2.5} /> : step.id}
              </span>
              <span className="workflow__label">{step.label}</span>
              {index < steps.length - 1 && (
                <span className="workflow__connector" aria-hidden="true" />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
