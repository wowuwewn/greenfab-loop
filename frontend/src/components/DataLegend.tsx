const legendItems = [
  {
    type: 'REAL',
    description: '실제 UCI SECOM 및 실제 모델 결과',
  },
  {
    type: 'DEMO',
    description: 'SECOM에 없는 자원·수요처 등 MVP 합성 데이터',
  },
  {
    type: 'SCENARIO',
    description: '사용자 입력값과 계산식 기반 ESG 결과',
  },
]

export function DataLegend() {
  return (
    <footer className="data-legend" aria-label="데이터 구분">
      <strong className="data-legend__title">데이터 구분</strong>
      <ul>
        {legendItems.map((item) => (
          <li key={item.type}>
            <span className={`data-legend__badge is-${item.type.toLowerCase()}`}>
              {item.type}
            </span>
            <p>{item.description}</p>
          </li>
        ))}
      </ul>
    </footer>
  )
}
