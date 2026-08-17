"use client";

import {
  useMemo,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  ArrowRight,
  BarChart3,
  Bot,
  Building2,
  ChevronDown,
  CircleHelp,
  ClipboardCheck,
  Gauge,
  LayoutDashboard,
  ListChecks,
  Recycle,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
} from "lucide-react";
import { dashboardData, type RiskItem } from "./dashboard-data";
import LoopWorkspace from "./loop-workspace";

const tabs = [
  ["loop", "운영 워크스페이스", "CASE WORKSPACE", ClipboardCheck, "WORKSPACE"],
  ["risks", "처리 대기 건", "CASE QUEUE", ListChecks, "WORKSPACE"],
  ["overview", "운영 개요", "OPERATIONS OVERVIEW", LayoutDashboard, "WORKSPACE"],
  ["performance", "모델 검증", "MODEL VALIDATION", BarChart3, "ANALYTICS"],
  ["simulator", "ESG 시뮬레이터", "ESG SIMULATOR", SlidersHorizontal, "ANALYTICS"],
  ["copilot", "설명 코파일럿", "GROUNDED EXPLAINER", Bot, "ANALYTICS"],
] as const;

type TabId = (typeof tabs)[number][0];
type ReviewFilter = "전체" | "실제 불량" | "실제 정상";
type RecallMode = "cv" | "temporal";

const nf = new Intl.NumberFormat("ko-KR");
const krw = new Intl.NumberFormat("ko-KR", {
  style: "currency",
  currency: "KRW",
  maximumFractionDigits: 0,
});

const modelNames: Record<string, string> = {
  "Logistic Regression": "로지스틱 회귀",
  "Random Forest": "랜덤 포레스트",
  XGBoost: "XGBoost",
  LightGBM: "LightGBM",
};

const metrics = [
  ["recall", "Recall", "#0b5d45"],
  ["precision", "Precision", "#42806a"],
  ["f1", "F1", "#79a18f"],
  ["pr_auc", "PR-AUC", "#d1a45d"],
] as const;

const selectedModel = dashboardData.model_comparison.find(
  (model) => model.model === dashboardData.summary.선정모델명,
)!;
const selectedMetrics = dashboardData.selected_model_metrics;
const top20 = dashboardData.inspection_strategies.find(
  (strategy) => strategy.fraction === 0.2,
)!;

function percent(value: number, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}

function modelLabel(value: string) {
  return modelNames[value] ?? value;
}

function riskClass(grade: string) {
  return grade === "고위험" ? "high" : grade === "중위험" ? "medium" : "low";
}

function RiskBadge({ grade }: { grade: string }) {
  return <span className={`risk-badge ${riskClass(grade)}`}>{grade}</span>;
}

function HeaderBlock({
  eyebrow,
  title,
  side,
}: {
  eyebrow: string;
  title: string;
  side?: ReactNode;
}) {
  return (
    <div className="card-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {side}
    </div>
  );
}

function Kpi({
  label,
  value,
  note,
  danger,
}: {
  label: string;
  value: string;
  note: string;
  danger?: boolean;
}) {
  return (
    <article className={`kpi ${danger ? "danger" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function RiskDonut() {
  const { high, medium, low } = dashboardData.risk_distribution;
  const total = high + medium + low;
  const highEnd = (high / total) * 100;
  const mediumEnd = highEnd + (medium / total) * 100;
  const background = `conic-gradient(#b42318 0 ${highEnd}%, #d9872f ${highEnd}% ${mediumEnd}%, #98a39c ${mediumEnd}% 100%)`;
  const rows = [
    ["고위험", high, "#b42318"],
    ["중위험", medium, "#d9872f"],
    ["저위험", low, "#98a39c"],
  ] as const;

  return (
    <div className="donut-layout">
      <div
        className="donut"
        style={{ background }}
        role="img"
        aria-label={`고위험 ${high}건, 중위험 ${medium}건, 저위험 ${low}건`}
      >
        <div>
          <strong>{nf.format(total)}</strong>
          <span>전체 생산 건</span>
        </div>
      </div>
      <div className="donut-legend">
        {rows.map(([label, value, color]) => (
          <div key={label}>
            <i style={{ background: color }} />
            <span>{label}</span>
            <strong>{nf.format(value)}건</strong>
            <small>{percent(value / total)}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function InspectionStrategies() {
  return (
    <article className="card inspection-card">
      <HeaderBlock
        eyebrow="CAPACITY PLANNING"
        title="검사 용량별 불량 포착"
        side={<span className="chip">OOF 후향 검증</span>}
      />
      <div className="inspection-list">
        {dashboardData.inspection_strategies.map((strategy) => (
          <div className={strategy.fraction === 0.2 ? "recommended" : ""} key={strategy.fraction}>
            <div>
              <span>상위 {Math.round(strategy.fraction * 100)}% 점검</span>
              {strategy.fraction === 0.2 && <b>권장 데모 시나리오</b>}
            </div>
            <strong>{percent(strategy.capture_rate, 2)}</strong>
            <p>
              {nf.format(strategy.inspection_count)}건 검사 · 불량 {strategy.captured_defects}/{strategy.total_defects}건 포함
            </p>
            <i>
              <b style={{ width: `${strategy.capture_rate * 100}%` }} />
            </i>
          </div>
        ))}
      </div>
      <p className="footnote compact-footnote">
        포착률은 실제 라벨을 이용한 내부 OOF 후향 평가입니다. 향후 생산 성능을 보장하는 수치가 아닙니다.
      </p>
    </article>
  );
}

function Overview({ onOpenQueue, onOpenWorkspace }: { onOpenQueue: () => void; onOpenWorkspace: () => void }) {
  const { summary, risk_distribution } = dashboardData;
  const top20DefectRate = top20.captured_defects / top20.inspection_count;
  const concentration = top20DefectRate / summary.불량률;
  const queueSteps = ["현장 확인", "Passport 작성", "매칭 검토", "추가 확인"];
  const queueActions = ["발생 여부 확인", "자원 정보 보완", "후보 조건 검토", "담당자 의견 확인"];

  return (
    <section className="tab-panel" role="tabpanel" id="panel-overview" aria-labelledby="tab-overview">
      <div className="overview-page-head">
        <div><span className="eyebrow">WORKSPACE / OPERATIONS OVERVIEW</span><h2>자원순환 운영센터</h2><p>생산 위험 신호부터 자원 활용 결정까지, 오늘 확인할 업무를 우선순위로 관리합니다.</p></div>
        <button type="button" onClick={onOpenQueue}>처리 대기 건 확인<ArrowRight aria-hidden="true" /></button>
      </div>

      <div className="operations-kpi-grid">
        <article><div><span>오늘 감지된 위험 신호</span><small className="source-tag demo">DEMO</small></div><strong>8<em>건</em></strong><p>상대 위험 상위 Case 기준</p></article>
        <article><div><span>현장 확인 대기</span><small className="source-tag demo">DEMO</small></div><strong>2<em>건</em></strong><p>가장 오래된 건 · 18분 경과</p></article>
        <article><div><span>매칭 검토 대기</span><small className="source-tag demo">DEMO</small></div><strong>1<em>건</em></strong><p>합성 입력 BGE-M3 후보 생성</p></article>
        <article><div><span>이번 달 순환 후보량</span><small className="source-tag scenario">SCENARIO</small></div><strong>12<em>kg</em></strong><p>검증된 감축 실적 아님</p></article>
      </div>

      <div className="operations-grid">
        <article className="case-queue-card">
          <div className="section-heading"><div><span>PRIORITY QUEUE</span><h3>우선 처리해야 할 Case</h3><p>위험 신호보다 현재 단계와 다음 행동을 중심으로 정렬했습니다.</p></div><button type="button" onClick={onOpenQueue}>전체 대기열</button></div>
          <div className="operations-table-wrap">
            <table className="operations-table">
              <thead><tr><th>우선순위</th><th>Case</th><th>현재 단계</th><th>경과 시간</th><th>다음 행동</th><th><span className="sr-only">열기</span></th></tr></thead>
              <tbody>
                {dashboardData.risk_items.slice(0, 4).map((item, index) => (
                  <tr key={item.id}>
                    <td><span className={`queue-priority p${index + 1}`}>{index + 1}</span></td>
                    <td><strong>{item.id}</strong><small>상대 위험 {item.risk_rank}위</small></td>
                    <td><span className="queue-stage">{queueSteps[index]}</span></td>
                    <td>{["18분", "12분", "7분", "4분"][index]}</td>
                    <td>{queueActions[index]}</td>
                    <td><button type="button" aria-label={`${item.id} 운영 워크스페이스 열기`} onClick={onOpenWorkspace}><ArrowRight aria-hidden="true" /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <aside className="operations-side">
          <article className="bottleneck-panel"><span>현재 병목 단계</span><strong>성분 분석 확인</strong><p>조건부 승인 전 필수 확인 1건이 남아 있습니다.</p><div><i style={{ width: "67%" }} /><span>2 / 3 완료</span></div><button type="button" onClick={onOpenWorkspace}>해당 Case 열기<ArrowRight aria-hidden="true" /></button></article>
          <article className="system-panel"><div><span>데이터 및 모델 상태</span><small>14:32 기준</small></div><ul><li><i className="ok" /><span><b>SECOM 분석</b><small>1,567건 OOF 결과 연결</small></span></li><li><i className="ok" /><span><b>BGE-M3 검색</b><small>12개 자원 스냅샷 검증</small></span></li><li><i className="demo" /><span><b>Resource Passport</b><small>합성 데모 입력</small></span></li></ul></article>
        </aside>
      </div>

      <div className="analytics-divider"><span>ANALYTICS EVIDENCE</span><h2>운영 판단을 뒷받침하는 분석 근거</h2><p>아래 수치는 후향 검증 결과이며 향후 생산 성능이나 감축 실적을 보장하지 않습니다.</p></div>

      <div className="insight-banner">
        <b>20%</b>
        <div>
          <span>검사 자원 집중 전략</span>
          <strong>
            전체의 20%인 {nf.format(top20.inspection_count)}건을 먼저 점검하면 불량 {top20.captured_defects}/{top20.total_defects}건을 포함합니다.
          </strong>
        </div>
        <small>포착률 {percent(top20.capture_rate, 2)}</small>
      </div>

      <div className="warning">
        <b>!</b>
        <strong>우선점검군 {nf.format(risk_distribution.high)}건</strong>
        <span>OOF 상대 위험 백분위 상위 약 20%로 정의한 데모 운영 등급입니다.</span>
      </div>

      <div className="kpi-grid">
        <Kpi label="총 생산 건수" value={nf.format(summary.총생산건수)} note="UCI SECOM 관측치" />
        <Kpi label="실제 불량 건수" value={nf.format(summary.불량건수)} note="전체의 6.64%" />
        <Kpi label="Top 20% 포착률" value={percent(top20.capture_rate, 2)} note={`${concentration.toFixed(2)}배 불량 집중`} />
        <Kpi label="우선점검군" value={nf.format(summary.고위험건수)} note="상대 위험 백분위 ≥ 80%" danger />
      </div>

      <div className="overview-grid">
        <article className="card">
          <HeaderBlock
            eyebrow="RISK DISTRIBUTION"
            title="전체 위험등급 분포"
            side={<span className="chip">확률이 아닌 상대순위</span>}
          />
          <RiskDonut />
        </article>

        <article className="card model-card">
          <HeaderBlock
            eyebrow="SELECTED MODEL"
            title="선정 모델 검증 결과"
            side={<span className="chip green">Precision 하한 통과</span>}
          />
          <div className="model-name">
            <b>M</b>
            <div>
              <span>Stratified 5-Fold + 학습 Fold 내부 임계값 튜닝</span>
              <strong>{modelLabel(summary.선정모델명)}</strong>
            </div>
          </div>
          <div className="metric-kpis four">
            <div><span>Recall</span><strong>{percent(selectedMetrics.recall)}</strong></div>
            <div><span>Precision</span><strong>{percent(selectedMetrics.precision)}</strong></div>
            <div><span>PR-AUC</span><strong>{percent(selectedMetrics.pr_auc)}</strong></div>
            <div><span>Balanced Acc.</span><strong>{percent(selectedMetrics.balanced_accuracy)}</strong></div>
          </div>
          <div className="selection-reason">
            <strong>왜 LightGBM인가요?</strong>
            <p>
              XGBoost의 Recall은 더 높지만 Precision이 {percent(selectedModel.precision)}입니다. LightGBM은 네 모델 중 유일하게 평균 Precision 15% 하한을 넘겨 선정됐습니다.
            </p>
          </div>
          <div className="threshold">
            <span>임시 배포 참고 임계값</span>
            <strong>{summary.선정임계값.toFixed(4)}</strong>
            <p>혼동행렬에는 단일값이 아니라 각 Fold에서 독립적으로 선택한 임계값을 사용했습니다.</p>
          </div>
        </article>
      </div>

      <div className="overview-lower">
        <InspectionStrategies />
        <article className="card robustness-mini">
          <HeaderBlock
            eyebrow="ROBUSTNESS CHECK"
            title="마지막 20% 행 구간 점검"
            side={<span className="chip alert-chip">성능 하락 확인</span>}
          />
          <div className="robustness-metrics">
            <div><span>Recall</span><strong>{percent(dashboardData.temporal_holdout.recall, 2)}</strong></div>
            <div><span>PR-AUC</span><strong>{percent(dashboardData.temporal_holdout.pr_auc, 2)}</strong></div>
            <div><span>Top 20% 포착</span><strong>{percent(dashboardData.temporal_holdout.top20_capture.capture_rate, 2)}</strong></div>
          </div>
          <p>
            Excel에 시각 열이 없어 행 순서가 시간순이라는 가정으로만 확인했습니다. 최신 현장 데이터 재학습과 설비·제품별 외부검증이 필요합니다.
          </p>
        </article>
      </div>

      <div className="info-note">
        <b>i</b>
        <p>
          원본에는 익명 센서 변수 590개가 있고, 팀 전처리 입력은 446개, Fold 내부 근상수 제거 후 440개를 사용했습니다. 위험점수는 보정된 불량확률이 아니며 SHAP은 물리적 원인이나 인과관계를 뜻하지 않습니다.
        </p>
      </div>
    </section>
  );
}

function LocalFactors({ item }: { item: RiskItem }) {
  const max = Math.max(...item.top_factors.map((factor) => Math.abs(factor.contribution)), 0.001);
  const positiveCount = item.top_factors.filter((factor) => factor.contribution > 0).length;

  return (
    <aside className="card factors">
      <HeaderBlock
        eyebrow="VALIDATION-ONLY LOCAL SHAP"
        title="선택 건 설명"
        side={<RiskBadge grade={item.risk_grade} />}
      />
      <div className="selected-item">
        <span>선택 생산 건</span>
        <strong>{item.id}</strong>
        <div>
          <span>OOF 상대 위험순위</span>
          <b>{item.risk_rank}위 / {dashboardData.summary.총생산건수}건</b>
        </div>
        <div>
          <span>검증용 실제 라벨</span>
          <b className={item.observed_label === "불량" ? "label-defect" : ""}>{item.observed_label}</b>
        </div>
      </div>
      <div className="explain-summary">
        상위 기여요인 5개 중 {positiveCount}개가 모델 위험점수를 높이는 방향으로 작용했습니다.
      </div>
      <div className="factor-legend">
        <span><i className="up" />위험 증가</span>
        <span><i className="down" />위험 감소</span>
      </div>
      <div className="factor-list">
        {item.top_factors.map((factor) => {
          const positive = factor.contribution >= 0;
          const width = Math.max((Math.abs(factor.contribution) / max) * 48, 2);
          return (
            <div className="factor" key={factor.feature}>
              <div>
                <span>{factor.display_feature}</span>
                <small>관측값 {nf.format(factor.feature_value)}</small>
                <strong className={positive ? "up-text" : "down-text"}>
                  {positive ? "+" : ""}{factor.contribution.toFixed(3)}
                </strong>
              </div>
              <div className="factor-track">
                <i className="mid" />
                <i className={positive ? "bar-up" : "bar-down"} style={{ width: `${width}%` }} />
              </div>
            </div>
          );
        })}
      </div>
      <p className="footnote">
        센서명이 익명화되어 실제 온도·압력·설비 변수로 번역할 수 없습니다. SHAP은 모델 예측의 연관 기여도이며 불량 원인이나 공정 조정 권고가 아닙니다.
      </p>
    </aside>
  );
}

function Risks() {
  const [filter, setFilter] = useState<ReviewFilter>("전체");
  const [selectedId, setSelectedId] = useState(dashboardData.risk_items[0].id);
  const filtered = useMemo(() => {
    if (filter === "전체") return dashboardData.risk_items;
    const label = filter === "실제 불량" ? "불량" : "정상";
    return dashboardData.risk_items.filter((item) => item.observed_label === label);
  }, [filter]);
  const selected = filtered.find((item) => item.id === selectedId) ?? filtered[0] ?? dashboardData.risk_items[0];

  return (
    <section className="tab-panel" role="tabpanel" id="panel-risks" aria-labelledby="tab-risks">
      <div className="warning top-warning">
        <b>!</b>
        <strong>위험순위 상위 30건 — 우선점검 대기열</strong>
        <span>30건 모두 전체 위험 백분위 상위 20%에 포함됩니다.</span>
      </div>
      <div className="section-bar">
        <div>
          <span className="eyebrow">RISK QUEUE</span>
          <h2>생산 건별 점검 우선순위</h2>
        </div>
        <div className="filters" aria-label="검증 라벨 필터">
          {(["전체", "실제 불량", "실제 정상"] as ReviewFilter[]).map((label) => (
            <button
              type="button"
              key={label}
              className={filter === label ? "active" : ""}
              aria-pressed={filter === label}
              onClick={() => setFilter(label)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="risk-grid">
        <article className="card table-card">
          <div className="table-meta">
            <span>{filter} 결과 · 검증용 실제 라벨은 운영 시점에 알 수 없습니다.</span>
            <strong>{filtered.length}건</strong>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>순위</th>
                  <th>생산 ID</th>
                  <th>상대 위험 백분위</th>
                  <th>등급</th>
                  <th>실제</th>
                  <th><span className="sr-only">상세 보기</span></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr
                    key={item.id}
                    className={selected.id === item.id ? "selected" : ""}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <td>{String(item.risk_rank).padStart(2, "0")}</td>
                    <td><strong>{item.id}</strong></td>
                    <td>
                      <div className="score">
                        <b>{percent(item.risk_score)}</b>
                        <span><i style={{ width: `${item.risk_score * 100}%` }} /></span>
                      </div>
                    </td>
                    <td><RiskBadge grade={item.risk_grade} /></td>
                    <td><span className={`observed ${item.observed_label === "불량" ? "defect" : "normal"}`}>{item.observed_label}</span></td>
                    <td>
                      <button
                        type="button"
                        className="row-select"
                        aria-label={`${item.id}, 위험순위 ${item.risk_rank}위 상세 보기`}
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedId(item.id);
                        }}
                      >
                        ›
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
        <LocalFactors item={selected} />
      </div>
    </section>
  );
}

function ModelChart() {
  return (
    <div className="chart-shell">
      <div className="chart-legend">
        {metrics.map(([, label, color]) => (
          <span key={label}><i style={{ background: color }} />{label}</span>
        ))}
      </div>
      <div className="bar-chart" role="img" aria-label="네 개 모델의 Recall, Precision, F1, PR-AUC 비교">
        {[100, 75, 50, 25, 0].map((value) => (
          <span className={`grid g${value}`} key={value}><b>{value}</b></span>
        ))}
        {dashboardData.model_comparison.map((model) => (
          <div className={`model-group ${model.model === dashboardData.summary.선정모델명 ? "chosen" : ""}`} key={model.model}>
            <div className="bars">
              {metrics.map(([key, label, color]) => (
                <div
                  className="vbar"
                  key={key}
                  style={{ height: `${model[key] * 100}%`, background: color }}
                  title={`${label} ${percent(model[key])}`}
                >
                  <span>{Math.round(model[key] * 100)}</span>
                </div>
              ))}
            </div>
            <strong>{modelLabel(model.model)}</strong>
          </div>
        ))}
      </div>
      <div className="sr-only">
        {dashboardData.model_comparison.map((model) => (
          <p key={model.model}>
            {modelLabel(model.model)}: Recall {percent(model.recall, 2)}, Precision {percent(model.precision, 2)}, F1 {percent(model.f1, 2)}, PR-AUC {percent(model.pr_auc, 2)}.
          </p>
        ))}
      </div>
    </div>
  );
}

function Performance() {
  const cm = dashboardData.confusion_matrix;
  const max = dashboardData.top_features[0]?.shap_value ?? 1;

  return (
    <section className="tab-panel" role="tabpanel" id="panel-performance" aria-labelledby="tab-performance">
      <article className="card performance-card">
        <HeaderBlock
          eyebrow="STRATIFIED 5-FOLD VALIDATION"
          title="모델별 OOF 성능 비교"
          side={<span className="chip">선정: {modelLabel(dashboardData.summary.선정모델명)}</span>}
        />
        <ModelChart />
        <div className="why">
          <strong>왜 Accuracy가 아닌가요?</strong>
          <span>불량이 6.64%뿐이므로 전체 정확도보다 불량 포착률(Recall)과 희소 양성 예측력(PR-AUC)이 운영 판단에 더 유효합니다.</span>
        </div>
      </article>

      <div className="performance-grid">
        <article className="card matrix-card">
          <HeaderBlock
            eyebrow="POOLED OOF CLASSIFICATION"
            title="혼동행렬"
            side={<span className="chip green">합계 {nf.format(cm.tp + cm.fp + cm.fn + cm.tn)}건</span>}
          />
          <div className="matrix-title">예측 알림</div>
          <div className="matrix">
            <i /><b>알림 없음</b><b>점검 알림</b>
            <b>실제 정상</b>
            <div className="correct"><span>TN</span><strong>{nf.format(cm.tn)}</strong><small>정상 미알림</small></div>
            <div className="false"><span>FP</span><strong>{nf.format(cm.fp)}</strong><small>추가 점검</small></div>
            <b>실제 불량</b>
            <div className="missed"><span>FN</span><strong>{nf.format(cm.fn)}</strong><small>놓친 불량</small></div>
            <div className="correct"><span>TP</span><strong>{nf.format(cm.tp)}</strong><small>불량 포착</small></div>
          </div>
          <p className="cv-note">
            Recall {percent(selectedMetrics.recall, 2)} ± {percent(selectedMetrics.recall_std ?? 0, 2)} · 각 행은 해당 Outer Fold 학습 데이터 안에서 선택한 임계값을 사용했습니다.
          </p>
        </article>

        <article className="card shap-card">
          <HeaderBlock
            eyebrow="GLOBAL OOF SHAP"
            title="전역 중요 센서 상위 15개"
            side={<span className="chip">mean |SHAP|</span>}
          />
          <div className="feature-list">
            {dashboardData.top_features.map((feature, index) => (
              <div key={feature.feature}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{feature.display_feature}</strong>
                <i><b style={{ width: `${(feature.shap_value / max) * 100}%` }} /></i>
                <small>{feature.shap_value.toFixed(3)}</small>
              </div>
            ))}
          </div>
        </article>
      </div>

      <div className="validation-grid">
        <article className="card validation-policy">
          <HeaderBlock eyebrow="SELECTION POLICY" title="선정·임계값 정책" />
          <ol>
            <li><b>동일 분할 비교</b><span>네 모델을 같은 Stratified 5-Fold로 비교</span></li>
            <li><b>학습 Fold 내부 선택</b><span>내부 3-Fold에서 Precision 15% 이상 중 Recall 최대 임계값 탐색</span></li>
            <li><b>모델 선정</b><span>평균 Precision 15% 이상 모델 중 평균 Recall 최대</span></li>
          </ol>
          <p>알고리즘 선택 자체를 별도의 최외곽 평가로 감싼 완전한 Nested model-selection은 아닙니다.</p>
        </article>
        <article className="card drift-card">
          <HeaderBlock eyebrow="ROW-ORDER ROBUSTNESS" title="시간구간 성능 민감도" side={<span className="chip alert-chip">외부검증 필요</span>} />
          <div className="drift-compare">
            <div><span>층화 CV Recall</span><strong>{percent(selectedMetrics.recall, 2)}</strong></div>
            <i>→</i>
            <div><span>마지막 20% Recall</span><strong>{percent(dashboardData.temporal_holdout.recall, 2)}</strong></div>
          </div>
          <p>{dashboardData.temporal_holdout.assumption}</p>
        </article>
      </div>

      <div className="info-note">
        <b>i</b>
        <p>팀 전처리 Excel은 전체 데이터 중앙값으로 이미 결측치를 대체했기 때문에 원자료부터 완전한 누수 방지 검증은 아닙니다. 직접적인 정답 누수는 확인되지 않았지만 성능 해석 시 이 한계를 함께 봐야 합니다.</p>
      </div>
    </section>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  onChange: (value: number) => void;
}) {
  const progress = ((value - min) / (max - min)) * 100;
  const inputId = `scenario-${label.replace(/\s+/g, "-")}`;
  return (
    <div className="slider">
      <div>
        <label htmlFor={`${inputId}-number`}>{label}</label>
        <div>
          <input
            id={`${inputId}-number`}
            type="number"
            value={value}
            min={min}
            max={max}
            step={step}
            onChange={(event) => onChange(Math.max(min, Math.min(max, Number(event.target.value))))}
          />
          <b>{unit}</b>
        </div>
      </div>
      <input
        id={`${inputId}-range`}
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        style={{ "--progress": `${progress}%` } as CSSProperties}
        aria-label={`${label} 조절`}
        aria-valuetext={`${nf.format(value)} ${unit}`}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <small><span>{nf.format(min)}</span><span>{nf.format(max)}</span></small>
    </div>
  );
}

function Result({
  icon,
  label,
  value,
  note,
}: {
  icon: string;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <article className="result">
      <b>{icon}</b>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function Simulator() {
  const defaults = dashboardData.scenario_defaults;
  const [production, setProduction] = useState(defaults.monthly_production);
  const [energyPer, setEnergyPer] = useState(defaults.rework_energy_kwh_per_defect);
  const [wastePer, setWastePer] = useState(defaults.waste_kg_per_defect);
  const [unitCost, setUnitCost] = useState(defaults.unit_cost_krw);
  const [success, setSuccess] = useState(defaults.action_success_rate * 100);
  const [recallMode, setRecallMode] = useState<RecallMode>("cv");
  const recall = recallMode === "cv" ? selectedMetrics.recall : dashboardData.temporal_holdout.recall;
  const potential = production * dashboardData.summary.불량률 * recall * (success / 100);
  const energy = potential * energyPer;
  const waste = potential * wastePer;
  const carbon = (energy / 1000) * defaults.emission_factor_tco2eq_per_mwh;
  const savings = potential * unitCost;

  const reset = () => {
    setProduction(defaults.monthly_production);
    setEnergyPer(defaults.rework_energy_kwh_per_defect);
    setWastePer(defaults.waste_kg_per_defect);
    setUnitCost(defaults.unit_cost_krw);
    setSuccess(defaults.action_success_rate * 100);
    setRecallMode("cv");
  };

  return (
    <section className="tab-panel" role="tabpanel" id="panel-simulator" aria-labelledby="tab-simulator">
      <div className="sim-intro">
        <div>
          <span className="eyebrow">WHAT-IF ANALYSIS</span>
          <h2>불량 예방의 환경·비용 효과를 조건별로 비교하세요.</h2>
          <p>실제 감축 실적을 주장하지 않고, 입력값과 선택한 검증 Recall을 적용한 조건부 시나리오만 계산합니다.</p>
        </div>
        <span className="chip green">불량률 {percent(dashboardData.summary.불량률, 2)} · 적용 Recall {percent(recall, 2)}</span>
      </div>

      <div className="recall-toggle" role="group" aria-label="시뮬레이션 Recall 기준">
        <button type="button" className={recallMode === "cv" ? "active" : ""} onClick={() => setRecallMode("cv")}>
          <span>기본 내부검증</span><strong>{percent(selectedMetrics.recall, 2)}</strong><small>Stratified 5-Fold OOF</small>
        </button>
        <button type="button" className={recallMode === "temporal" ? "active conservative" : "conservative"} onClick={() => setRecallMode("temporal")}>
          <span>보수적 민감도</span><strong>{percent(dashboardData.temporal_holdout.recall, 2)}</strong><small>마지막 20% 행 구간</small>
        </button>
      </div>

      <div className="sim-grid">
        <article className="card inputs">
          <HeaderBlock eyebrow="INPUT CONDITIONS" title="시나리오 조건" side={<button type="button" onClick={reset}>기본값 복원</button>} />
          <div className="sliders">
            <Slider label="월 생산량" value={production} min={1000} max={100000} step={1000} unit="건" onChange={setProduction} />
            <Slider label="불량 1건당 재작업 전력량" value={energyPer} min={1} max={50} step={1} unit="kWh" onChange={setEnergyPer} />
            <Slider label="불량 1건당 폐기 중량" value={wastePer} min={0.1} max={10} step={0.1} unit="kg" onChange={setWastePer} />
            <Slider label="제품 1개당 원가" value={unitCost} min={10000} max={1000000} step={10000} unit="원" onChange={setUnitCost} />
            <Slider label="공정조정 성공률" value={success} min={0} max={100} step={1} unit="%" onChange={setSuccess} />
          </div>
        </article>

        <div className="results" aria-live="polite" aria-atomic="true">
          <div className="prevented">
            <div><span>월 잠재 예방 불량</span><strong>{nf.format(Math.round(potential))}건</strong></div>
            <p>생산량 × 불량률 × 적용 Recall × 공정조정 성공률</p>
          </div>
          <div className="result-grid">
            <Result icon="E" label="예상 전력 절감량" value={`${nf.format(Math.round(energy))} kWh`} note={`${(energy / 1000).toFixed(2)} MWh`} />
            <Result icon="W" label="예상 폐기물 감소량" value={`${nf.format(Math.round(waste))} kg`} note="입력한 폐기 중량 가정" />
            <Result icon="C" label="예상 탄소 감축량" value={`${carbon.toFixed(2)} tCO₂eq`} note={`전력배출계수 ${defaults.emission_factor_tco2eq_per_mwh}`} />
            <Result icon="₩" label="예상 원가 절감액" value={krw.format(Math.round(savings))} note="입력한 제품 원가 기준" />
          </div>
        </div>
      </div>

      <div className="disclaimer">
        <b>i</b>
        <p><strong>시나리오 분석 안내</strong> {defaults.disclaimer} 오탐 점검비용, 공정 개입비용, 설비별 에너지와 탄소계수 변동은 포함하지 않습니다.</p>
      </div>
    </section>
  );
}

type CopilotAnswer = {
  title: string;
  body: string;
  sources: string[];
  caution?: string;
};

type CopilotMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  answer?: CopilotAnswer;
};

function findRiskItem(question: string) {
  const match = question.match(/SECOM[-_\s]?(\d{1,6})/i);
  if (!match) return null;
  const normalized = `SECOM-${match[1].padStart(4, "0")}`;
  return dashboardData.risk_items.find((item) => item.id === normalized) ?? null;
}

function buildGroundedAnswer(question: string, fallbackItem: RiskItem): CopilotAnswer {
  const normalized = question.trim().toLowerCase();
  const item = findRiskItem(question);

  if (item) {
    const rising = item.top_factors.filter((factor) => factor.contribution > 0).slice(0, 3);
    const falling = item.top_factors.filter((factor) => factor.contribution < 0).slice(0, 2);
    return {
      title: `${item.id} 점검 근거`,
      body: `${item.id}는 전체 ${dashboardData.summary.총생산건수}건 중 상대 위험순위 ${item.risk_rank}위입니다. 모델 위험점수를 크게 높인 요인은 ${rising.map((factor) => `${factor.display_feature}(${factor.contribution.toFixed(3)})`).join(", ")}입니다.${falling.length ? ` 반대로 ${falling.map((factor) => factor.display_feature).join(", ")}는 위험점수를 낮추는 방향으로 작용했습니다.` : ""} 검증용 실제 라벨은 '${item.observed_label}'이지만, 운영 시점에는 이 정답을 알 수 없습니다.`,
      sources: ["risk_items", "OOF 상대 위험순위", "개별 OOF SHAP Top 5"],
      caution: "센서의 실제 공정 의미가 비공개이므로 설비·LOT·공정이력과 대조한 2차 점검이 필요합니다.",
    };
  }

  if (/모델|lightgbm|xgboost|선정|성능/.test(normalized)) {
    const xgb = dashboardData.model_comparison.find((model) => model.model === "XGBoost")!;
    return {
      title: "LightGBM 선정 이유",
      body: `XGBoost의 평균 Recall은 ${percent(xgb.recall, 2)}로 더 높지만 Precision은 ${percent(xgb.precision, 2)}였습니다. 사전에 정한 평균 Precision 15% 하한을 통과한 모델은 LightGBM(${percent(selectedModel.precision, 2)})뿐이어서 선정했습니다. 선정 모델의 pooled OOF Recall은 ${percent(selectedMetrics.recall, 2)}, Balanced Accuracy는 ${percent(selectedMetrics.balanced_accuracy, 2)}입니다.`,
      sources: ["model_comparison", "selected_model_metrics", "model_selection_rule"],
      caution: "같은 CV 결과로 알고리즘을 선택·보고했으므로 완전한 Nested model-selection 추정치는 아닙니다.",
    };
  }

  if (/shap|센서|변수|원인|기여/.test(normalized)) {
    const leaders = dashboardData.top_features.slice(0, 3).map((feature) => feature.display_feature).join(", ");
    return {
      title: "SHAP 해석 범위",
      body: `전역 OOF SHAP 상위 센서는 ${leaders}입니다. SHAP은 모델 예측을 얼마나 어느 방향으로 움직였는지 설명하지만, SECOM 센서가 익명화되어 온도·압력·가스 유량 같은 실제 공정명으로 번역할 수 없습니다. 따라서 SHAP은 원인 규명이 아니라 현장 엔지니어가 추가 확인할 센서 ID를 좁히는 근거로 사용합니다.`,
      sources: ["top_features", "metadata.limitations", "OOF SHAP"],
      caution: "상관 센서 사이에서는 중요도가 분산될 수 있으며 인과관계를 의미하지 않습니다.",
    };
  }

  if (/20%|포착|점검|검사|우선/.test(normalized)) {
    const groupRate = top20.captured_defects / top20.inspection_count;
    return {
      title: "상위 20% 우선점검 전략",
      body: `내부 OOF 평가에서 위험순위 상위 20%인 ${top20.inspection_count}건에 실제 불량 ${top20.captured_defects}/${top20.total_defects}건이 포함돼 포착률은 ${percent(top20.capture_rate, 2)}였습니다. 이 점검군의 불량률은 ${percent(groupRate, 2)}로 전체 불량률 ${percent(dashboardData.summary.불량률, 2)}의 ${(groupRate / dashboardData.summary.불량률).toFixed(2)}배입니다.`,
      sources: ["inspection_strategies", "summary", "OOF 위험순위"],
      caution: "후향 내부검증 결과이며 실제 현장 포착률을 보장하지 않습니다.",
    };
  }

  if (/시간|마지막|최신|드리프트|일반화|강건/.test(normalized)) {
    const temporal = dashboardData.temporal_holdout;
    return {
      title: "시간구간 강건성 경고",
      body: `마지막 20% 행 구간에서 Recall은 ${percent(temporal.recall, 2)}, PR-AUC는 ${percent(temporal.pr_auc, 2)}, Top 20% 포착률은 ${percent(temporal.top20_capture.capture_rate, 2)}로 하락했습니다. 이는 무작위 층화 CV만으로 미래 성능을 낙관하면 안 된다는 신호입니다.`,
      sources: ["temporal_holdout", "row-order robustness"],
      caution: temporal.assumption,
    };
  }

  if (/esg|탄소|전력|폐기|원가|절감/.test(normalized)) {
    const defaults = dashboardData.scenario_defaults;
    const potential = defaults.monthly_production * dashboardData.summary.불량률 * selectedMetrics.recall * defaults.action_success_rate;
    const energy = potential * defaults.rework_energy_kwh_per_defect;
    const waste = potential * defaults.waste_kg_per_defect;
    const carbon = (energy / 1000) * defaults.emission_factor_tco2eq_per_mwh;
    const savings = potential * defaults.unit_cost_krw;
    return {
      title: "기본 ESG 시나리오",
      body: `월 생산 ${nf.format(defaults.monthly_production)}건, 공정조정 성공률 ${percent(defaults.action_success_rate)}, 선정 모델 Recall ${percent(selectedMetrics.recall, 2)}를 적용하면 잠재 예방 불량은 약 ${nf.format(Math.round(potential))}건입니다. 입력 가정상 전력 ${nf.format(Math.round(energy))}kWh, 폐기물 ${nf.format(Math.round(waste))}kg, 탄소 ${carbon.toFixed(2)}tCO₂eq, 원가 약 ${krw.format(Math.round(savings))}의 잠재효과가 계산됩니다.`,
      sources: ["scenario_defaults", "selected_model_metrics", "summary"],
      caution: defaults.disclaimer,
    };
  }

  if (/한계|리스크|주의|신뢰|확률/.test(normalized)) {
    return {
      title: "현재 결과의 핵심 한계",
      body: dashboardData.metadata.limitations.slice(0, 4).join(" "),
      sources: ["metadata.limitations", "run methodology"],
      caution: "본 서비스는 자동 폐기·공정제어가 아니라 사람의 2차 검사를 돕는 우선순위 의사결정 프로토타입입니다.",
    };
  }

  return {
    title: "질문을 더 구체적으로 입력해 주세요",
    body: `예: '${fallbackItem.id}는 왜 위험해?', 'LightGBM을 왜 선택했어?', '상위 20% 포착률은 무슨 뜻이야?', 'SHAP 센서를 실제 공정 원인으로 볼 수 있어?', '시간구간 검증 결과를 설명해줘'처럼 질문할 수 있습니다.`,
    sources: ["dashboard_data.json"],
    caution: "설명 엔진은 제공된 JSON 근거 밖의 숫자나 익명 센서 의미를 생성하지 않습니다.",
  };
}

const quickQuestions = [
  "상위 20% 우선점검 전략을 설명해줘",
  "LightGBM을 왜 선택했어?",
  "SHAP 센서를 실제 공정 원인으로 볼 수 있어?",
  "마지막 20% 구간에서 왜 성능이 낮아졌어?",
];

function Copilot() {
  const firstRisk = dashboardData.risk_items[0];
  const [selectedId, setSelectedId] = useState(firstRisk.id);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<CopilotMessage[]>([
    {
      id: 1,
      role: "assistant",
      text: "",
      answer: {
        title: "GreenFab 설명 코파일럿",
        body: "모델·점검전략·생산 건·SHAP·ESG·한계에 대해 질문해 보세요. 모든 답변은 현재 dashboard_data.json의 수치만 사용합니다.",
        sources: ["dashboard_data.json", "근거 제한 안전 모드"],
        caution: "이 설명 계층은 불량을 새로 예측하거나 공정을 자동 제어하지 않습니다.",
      },
    },
  ]);
  const selected = dashboardData.risk_items.find((item) => item.id === selectedId) ?? firstRisk;

  const ask = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages((current) => {
      const nextId = (current.at(-1)?.id ?? 0) + 1;
      return [
        ...current,
        { id: nextId, role: "user", text: trimmed },
        { id: nextId + 1, role: "assistant", text: "", answer: buildGroundedAnswer(trimmed, selected) },
      ];
    });
    setQuestion("");
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    ask(question);
  };

  return (
    <section className="tab-panel" role="tabpanel" id="panel-copilot" aria-labelledby="tab-copilot">
      <div className="copilot-heading">
        <div>
          <span className="eyebrow">GROUNDED EXPLANATION LAYER</span>
          <h2>수치를 만들지 않는 설명 코파일럿</h2>
          <p>예측은 ML 모델이 수행하고, 설명 계층은 저장된 JSON 수치와 OOF SHAP을 쉬운 한국어로 풀어줍니다.</p>
        </div>
        <div className="engine-status"><i /><span>현재 모드</span><strong>근거 제한 안전 fallback</strong></div>
      </div>

      <div className="copilot-grid">
        <article className="card chat-card">
          <div className="chat-toolbar">
            <div><span>설명 대화</span><strong>숫자·센서명 생성 금지</strong></div>
            <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} aria-label="설명할 생산 건 선택">
              {dashboardData.risk_items.map((item) => (
                <option value={item.id} key={item.id}>{item.id} · 위험순위 {item.risk_rank}위</option>
              ))}
            </select>
          </div>

          <div className="message-log" role="log" aria-live="polite">
            {messages.map((message) => (
              <div className={`message ${message.role}`} key={message.id}>
                {message.role === "user" ? (
                  <p>{message.text}</p>
                ) : (
                  <div>
                    <span className="message-label">GREENFAB EXPLAINER</span>
                    <strong>{message.answer?.title}</strong>
                    <p>{message.answer?.body}</p>
                    <div className="source-chips">
                      {message.answer?.sources.map((source) => <span key={source}>{source}</span>)}
                    </div>
                    {message.answer?.caution && <small><b>주의</b>{message.answer.caution}</small>}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="quick-questions" aria-label="추천 질문">
            {quickQuestions.map((quick) => (
              <button type="button" key={quick} onClick={() => ask(quick)}>{quick}</button>
            ))}
            <button type="button" onClick={() => ask(`${selected.id}는 왜 위험해?`)}>{selected.id}는 왜 위험해?</button>
          </div>

          <form className="chat-input" onSubmit={submit}>
            <label className="sr-only" htmlFor="copilot-question">설명 질문</label>
            <input
              id="copilot-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="예: SECOM-0045는 왜 우선 점검 대상인가요?"
              autoComplete="off"
            />
            <button type="submit" disabled={!question.trim()}>질문하기</button>
          </form>
        </article>

        <aside className="copilot-side">
          <article className="card guardrail-card">
            <HeaderBlock eyebrow="GUARDRAILS" title="설명 안전장치" side={<span className="chip green">Demo ready</span>} />
            <ul>
              <li><b>JSON 단일 수치 원천</b><span>화면·설명·계산이 같은 결과 파일을 사용</span></li>
              <li><b>익명 센서 의미 추측 금지</b><span>온도·압력 등 실제 공정명 생성 금지</span></li>
              <li><b>원인·인과 단정 금지</b><span>SHAP을 예측 기여도로만 설명</span></li>
              <li><b>실패 시 정적 fallback</b><span>외부 모델 장애와 무관하게 핵심 설명 제공</span></li>
            </ul>
          </article>
          <article className="card scope-card">
            <HeaderBlock eyebrow="SCOPE" title="사용 범위" />
            <p>이 코파일럿은 분석 결과를 읽고 설명합니다. 신규 생산 건 추론, 자동 폐기, 공정 파라미터 변경은 수행하지 않습니다.</p>
            <div><span>판단 주체</span><strong>품질·공정 담당자</strong></div>
            <div><span>권장 다음 행동</span><strong>설비·LOT·공정이력 2차 대조</strong></div>
          </article>
        </aside>
      </div>
    </section>
  );
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("loop");
  const active = tabs.find((tab) => tab[0] === activeTab)!;

  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const direction = ["ArrowDown", "ArrowRight"].includes(event.key) ? 1 : -1;
    const next = (index + direction + tabs.length) % tabs.length;
    setActiveTab(tabs[next][0]);
    document.getElementById(`tab-${tabs[next][0]}`)?.focus();
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">본문으로 건너뛰기</a>
      <aside className="sidebar">
        <div className="brand">
          <b><Recycle aria-hidden="true" /></b>
          <div><strong>GreenFab</strong><span>Loop</span><small>Industrial Circularity OS</small></div>
        </div>
        <nav role="tablist" aria-label="서비스 화면">
          {(["WORKSPACE", "ANALYTICS"] as const).map((group) => (
            <div className="nav-group" key={group}>
              <span className="nav-label">{group}</span>
              {tabs.map((tab, index) => {
                if (tab[4] !== group) return null;
                const Icon = tab[3];
                return (
                  <button
                    id={`tab-${tab[0]}`}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === tab[0]}
                    aria-controls={`panel-${tab[0]}`}
                    tabIndex={activeTab === tab[0] ? 0 : -1}
                    className={activeTab === tab[0] ? "active" : ""}
                    key={tab[0]}
                    onClick={() => setActiveTab(tab[0])}
                    onKeyDown={(event) => onTabKey(event, index)}
                  >
                    <Icon className="nav-icon" aria-hidden="true" />
                    <span>{tab[1]}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="side-space" />
        <div className="dataset">
          <div className="dataset-head"><ShieldCheck aria-hidden="true" /><span>검증 환경</span></div>
          <strong>SECOM + BGE-M3</strong>
          <p>데이터 종류와 계산 근거를 분리해 표시하는 의사결정 지원 데모입니다.</p>
          <a href="https://archive.ics.uci.edu/dataset/179/secom" target="_blank" rel="noreferrer">원본 데이터 확인</a>
        </div>
        <div className="sidebar-user">
          <span><UserRound aria-hidden="true" /></span>
          <div><strong>환경·자원관리 담당자</strong><small>Demo workspace</small></div>
          <ChevronDown aria-hidden="true" />
        </div>
      </aside>

      <main id="main-content" tabIndex={-1}>
        <header>
          <div className="topbar-title">
            <span>GreenFab Loop <b>/</b> {active[2]}</span>
            <h1>{active[1]}</h1>
          </div>
          <div className="header-meta">
            <div className="plant-context"><Building2 aria-hidden="true" /><span><small>현재 사업장</small><strong>GreenFab Demo Manufacturing</strong></span></div>
            <div className="sync-context"><Gauge aria-hidden="true" /><span><small>데이터 상태</small><strong>검증 데이터 · 14:32 기준</strong></span></div>
            <span className="help-icon" aria-label="도움말 안내"><CircleHelp aria-hidden="true" /></span>
          </div>
        </header>
        <div className="content">
          {activeTab === "loop" && <LoopWorkspace />}
          {activeTab === "overview" && <Overview onOpenQueue={() => setActiveTab("risks")} onOpenWorkspace={() => setActiveTab("loop")} />}
          {activeTab === "risks" && <Risks />}
          {activeTab === "performance" && <Performance />}
          {activeTab === "simulator" && <Simulator />}
          {activeTab === "copilot" && <Copilot />}
        </div>
      </main>
    </div>
  );
}
