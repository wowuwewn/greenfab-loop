import { Building2, Factory, Recycle, RefreshCw } from 'lucide-react'

export function ServiceFlowVisual() {
  return (
    <section className="loop-network" aria-labelledby="loop-network-title">
      <header className="loop-network__header">
        <h2 id="loop-network-title">한눈에 보는 GreenFab Loop</h2>
        <p>발생한 자원을 다음 활용 경로로 연결합니다.</p>
      </header>

      <div className="network-card">
        <div className="network-stage">
          <span
            className="network-connector network-connector--left"
            aria-hidden="true"
          />
          <span
            className="network-connector network-connector--right"
            aria-hidden="true"
          />
          <span
            className="network-connector network-connector--top"
            aria-hidden="true"
          />
          <span
            className="network-connector network-connector--bottom"
            aria-hidden="true"
          />

          <div className="network-node network-node--top">
            <span className="network-node__icon" aria-hidden="true">
              <Recycle size={21} strokeWidth={1.7} />
            </span>
            <div className="network-node__copy">
              <strong>재활용사</strong>
            </div>
          </div>

          <div className="network-node network-node--left">
            <span className="network-node__icon is-source" aria-hidden="true">
              <Factory size={21} strokeWidth={1.7} />
            </span>
            <div className="network-node__copy">
              <strong>자원 발생 기업</strong>
              <small>공장 A</small>
            </div>
          </div>

          <div className="network-hub">
            <span className="network-hub__visual" aria-hidden="true">
              <span className="network-hub__ring" />
              <span className="network-hub__mark">
                <RefreshCw size={30} strokeWidth={1.8} />
              </span>
            </span>
            <div className="network-hub__copy">
              <strong>GreenFab Loop</strong>
              <p>AI 후보 탐색 · 규칙 확인 · 사람 결정 · 기록</p>
            </div>
          </div>

          <div className="network-node network-node--right">
            <span className="network-node__icon" aria-hidden="true">
              <Building2 size={21} strokeWidth={1.7} />
            </span>
            <div className="network-node__copy">
              <strong>활용 기업 B</strong>
            </div>
          </div>

          <div className="network-node network-node--bottom">
            <span className="network-node__icon" aria-hidden="true">
              <Building2 size={21} strokeWidth={1.7} />
            </span>
            <div className="network-node__copy">
              <strong>활용 기업 C</strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
