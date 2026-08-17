"use client";

import { useMemo, useState } from "react";
import {
  ArrowRight,
  BrainCircuit,
  Check,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Database,
  Download,
  FileCheck2,
  MapPin,
  PackageCheck,
  RotateCcw,
  Scale,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { dashboardData } from "./dashboard-data";
import { buildLoopContract, deriveCandidateStatus } from "./contract-adapter";
import datasetJson from "./loop_dataset.json";
import matchResultsJson from "./match_results.json";

type EvidenceKind = "REAL" | "DEMO" | "SCENARIO";
type Decision = "approved" | "hold" | "rejected";
type Occurrence = "pending" | "confirmed" | "not-found";
type Demand = (typeof datasetJson.demands)[number];
type RankedMatch = { rank: number; demandId: string; score: number };
type MatchResults = {
  generatedAt: string | null;
  engine: string;
  model: string;
  modelRevision: string;
  provenance: string;
  notice?: string;
  metrics: {
    resourceCount: number;
    demandCount: number;
    tfidfHitAt1: number;
    tfidfRecallAt3: number;
    embeddingHitAt1: number;
    embeddingRecallAt3: number;
  };
  results: Array<{
    resourceId: string;
    expectedDemandId: string;
    tfidfTop3: RankedMatch[];
    embeddingTop3: RankedMatch[];
    expectedFoundAt: number | null;
  }>;
};

const dataset = datasetJson;
const matchResults = matchResultsJson as unknown as MatchResults;

const demoResource = dataset.resources[0];
const initialMatchDemandId = matchResults.results.find((item) => item.resourceId === demoResource.id)?.embeddingTop3[0]?.demandId ?? demoResource.expectedDemandId;
const initialRisk = dashboardData.risk_items.find((item) => item.id === "SECOM-0116") ?? dashboardData.risk_items[0];
const decisionLabels: Record<Decision, string> = {
  approved: "조건부 승인",
  hold: "추가 확인",
  rejected: "검토 제외",
};

function EvidenceBadge({ kind, children }: { kind: EvidenceKind; children?: React.ReactNode }) {
  return <span className={`evidence-badge ${kind.toLowerCase()}`}>{children ?? kind}</span>;
}

function FieldLabel({ kind, children }: { kind: EvidenceKind; children: React.ReactNode }) {
  return <span className="field-label"><span>{children}</span><EvidenceBadge kind={kind} /></span>;
}

function percent(value: number, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}

function ruleStatus(demand: Demand, quantityKg: number, analysisComplete: boolean) {
  const quantityRange = "quantityRangeKg" in demand ? demand.quantityRangeKg : undefined;
  const requiresAnalysis = "requiresAnalysis" in demand ? demand.requiresAnalysis : undefined;
  const quantity = quantityRange ? quantityKg >= quantityRange[0] && quantityKg <= quantityRange[1] : null;
  const requiredInfo = requiresAnalysis === true ? analysisComplete : requiresAnalysis === false ? true : null;
  const missingFields = [
    ...(quantity === null ? ["quantity_rule"] : []),
    ...(requiredInfo === false ? ["composition"] : []),
    ...(requiredInfo === null ? ["required_info_rule"] : []),
  ];
  const ruleCheck = {
    quantity,
    required_info: requiredInfo,
    location: null,
    missing_fields: missingFields,
  };
  const status = deriveCandidateStatus(ruleCheck);
  if (status === "RULE_FAIL") return { label: "수량 조건 불일치", tone: "blocked", status, ruleCheck };
  if (requiredInfo === false) return { label: "성분 확인 후 검토", tone: "conditional", status, ruleCheck };
  if (status === "NEEDS_INFO") return { label: "규칙 정보 추가 필요", tone: "conditional", status, ruleCheck };
  return { label: "1차 조건 통과 · 사람 검토", tone: "pass", status, ruleCheck };
}

export default function LoopWorkspace() {
  const [selectedRiskId, setSelectedRiskId] = useState(initialRisk.id);
  const [occurrence, setOccurrence] = useState<Occurrence>("pending");
  const [confirmedAt, setConfirmedAt] = useState<string | null>(null);
  const [quantityKg, setQuantityKg] = useState(demoResource.quantityKg ?? 12);
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const [selectedDemandId, setSelectedDemandId] = useState(initialMatchDemandId);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [decidedAt, setDecidedAt] = useState<string | null>(null);
  const [decisionNote, setDecisionNote] = useState("");
  const [showBaseline, setShowBaseline] = useState(false);
  const [aiAcknowledged, setAiAcknowledged] = useState(false);
  const [receiptGeneratedAt, setReceiptGeneratedAt] = useState<string | null>(null);

  const selectedRisk = dashboardData.risk_items.find((item) => item.id === selectedRiskId) ?? initialRisk;
  const result = matchResults.results.find((item) => item.resourceId === demoResource.id);
  const rankedDemands = useMemo(() => {
    const rankings = (showBaseline ? result?.tfidfTop3 : result?.embeddingTop3) ?? [];
    const fallback = dataset.demands.slice(0, 3).map((demand, index) => ({ rank: index + 1, demandId: demand.id, score: 0 }));
    return (rankings.length ? rankings : fallback).map((ranking) => ({
      ...ranking,
      demand: dataset.demands.find((demand) => demand.id === ranking.demandId)!,
    }));
  }, [result, showBaseline]);
  const selectedDemand = dataset.demands.find((demand) => demand.id === selectedDemandId) ?? rankedDemands[0]?.demand ?? dataset.demands[0];
  const selectedRule = ruleStatus(selectedDemand, quantityKg, analysisComplete);
  const engineReady = matchResults.engine === "PRECOMPUTED_BGE_M3";
  const bgeFailureCount = matchResults.results.filter((item) => item.expectedFoundAt === null).length;
  const receiptId = `GF-DEMO-${selectedRisk.id.replace("SECOM-", "")}`;
  const passportId = `PASSPORT-DEMO-${selectedRisk.id.replace("SECOM-", "")}`;
  const quantityOk = selectedRule.ruleCheck.quantity === true;
  const canFinalize = occurrence === "confirmed" && decision !== null && aiAcknowledged && decisionNote.trim().length >= 10 && (decision !== "approved" || (analysisComplete && selectedRule.status === "REVIEW"));
  const nextAction = !analysisComplete
    ? "성분 정보가 없으면 보류 또는 제외로 기록하세요."
    : !aiAcknowledged
      ? "AI 유사도의 한계를 확인하세요."
      : decision === null
        ? "사람의 최종 상태를 선택하세요."
        : decisionNote.trim().length < 10
          ? "결정 사유를 10자 이상 입력하세요."
          : "Green Receipt 초안 JSON을 만들 수 있습니다.";
  const scenarioDiversionKg = decision === "approved" ? quantityKg : decision === null ? null : 0;
  const currentStep = receiptGeneratedAt ? 7 : decision ? 5 : aiAcknowledged ? 4 : analysisComplete ? 3 : occurrence === "confirmed" ? 2 : 1;
  const workflowSteps = [
    ["Detect", "위험 신호"],
    ["Confirm", "현장 확인"],
    ["Passport", "자원 정보"],
    ["Match", "후보 검색"],
    ["Decide", "사람 승인"],
    ["Scenario", "전환량 계산"],
    ["Prove", "근거 기록"],
  ] as const;

  const resetDemo = () => {
    setSelectedRiskId(initialRisk.id);
    setOccurrence("pending");
    setConfirmedAt(null);
    setQuantityKg(demoResource.quantityKg ?? 12);
    setAnalysisComplete(false);
    setSelectedDemandId(initialMatchDemandId);
    setDecision(null);
    setDecidedAt(null);
    setDecisionNote("");
    setShowBaseline(false);
    setAiAcknowledged(false);
    setReceiptGeneratedAt(null);
  };

  const changeEngine = (baseline: boolean) => {
    setShowBaseline(baseline);
    setDecision(null);
    setDecidedAt(null);
    setReceiptGeneratedAt(null);
    const nextTop = baseline ? result?.tfidfTop3[0] : result?.embeddingTop3[0];
    if (nextTop) setSelectedDemandId(nextTop.demandId);
  };

  const chooseOccurrence = (next: Exclude<Occurrence, "pending">) => {
    setOccurrence(next);
    setConfirmedAt(new Date().toISOString());
    setDecision(null);
    setDecidedAt(null);
    setDecisionNote("");
    setAiAcknowledged(false);
    setReceiptGeneratedAt(null);
  };

  const downloadReceipt = () => {
    if (!canFinalize || !decision || !decidedAt) return;
    const createdAt = new Date().toISOString();
    const candidates = rankedDemands.map(({ score, demand }) => {
      const rule = ruleStatus(demand, quantityKg, analysisComplete);
      return {
        demand_id: demand.id,
        company_name: demand.company,
        demand_description: `${demand.title}. ${demand.description}`,
        semantic_similarity: score || null,
        rule_check: rule.ruleCheck,
        status: rule.status,
      };
    });
    const payload = buildLoopContract({
      case_record: {
        case_id: selectedRisk.id,
        risk_rank: selectedRisk.risk_rank,
        shap_top_features: selectedRisk.top_factors.map((factor) => ({
          feature_name: factor.feature,
          shap_value: factor.contribution,
        })),
      },
      confirmation: {
        status: "CONFIRMED",
        confirmed_by: "demo_operator",
        confirmed_at: confirmedAt,
      },
      passport: {
        passport_id: passportId,
        description: `${demoResource.name}. ${demoResource.description}`,
        quantity: quantityKg,
        unit: "kg",
        condition: demoResource.state ?? null,
        location: demoResource.location ?? null,
        composition: analysisComplete && "composition" in demoResource ? (demoResource.composition ?? null) : null,
      },
      match: {
        model: showBaseline ? "char-ngram-tfidf-baseline" : matchResults.model,
        created_at: matchResults.generatedAt,
        candidates,
      },
      decision: {
        status: decision,
        selected_demand_id: selectedDemand.id,
        reason: decisionNote.trim(),
        decided_by: "demo_reviewer",
        decided_at: decidedAt,
      },
      receipt: {receipt_id: receiptId, created_at: createdAt},
    });
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${receiptId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setReceiptGeneratedAt(createdAt);
  };

  return (
    <section className="tab-panel loop-workspace" role="tabpanel" id="panel-loop" aria-labelledby="tab-loop">
      <div className="workspace-page-head">
        <div className="workspace-heading">
          <span className="loop-kicker">WORKSPACE / ACTIVE CASE</span>
          <div className="workspace-title-row">
            <h2>자원순환 운영 케이스</h2>
            <span className={`case-status ${analysisComplete ? "ready" : ""}`}><Clock3 aria-hidden="true" />{analysisComplete ? "최종 결정 준비" : "성분 분석 대기"}</span>
          </div>
          <p>생산 위험 신호를 확인하고, 실제 발생 자원의 다음 활용처와 최종 결정 근거를 관리합니다.</p>
        </div>
        <div className="workspace-actions">
          <span className={`engine-pill ${engineReady ? "ready" : "pending"}`}><ShieldCheck aria-hidden="true" />{engineReady ? "BGE-M3 스냅샷 로드됨" : "검색 결과 생성 대기"}</span>
          <button type="button" onClick={resetDemo}><RotateCcw aria-hidden="true" />데모 초기화</button>
        </div>
      </div>

      <div className="case-context" aria-label="현재 케이스 요약">
        <div className="case-identity"><span>CASE ID</span><strong>{selectedRisk.id}</strong><small>Golden demo</small></div>
        <dl>
          <div><dt>검토 우선순위</dt><dd><b>{selectedRisk.risk_rank}위</b> / {dashboardData.summary.총생산건수}건</dd></div>
          <div><dt>감지 시각</dt><dd>2026.08.18 · 14:02</dd></div>
          <div><dt>담당자</dt><dd><UserCheck aria-hidden="true" />환경·자원관리 담당자</dd></div>
          <div><dt>데이터 출처</dt><dd><Database aria-hidden="true" />SECOM OOF 분석</dd></div>
        </dl>
        <div className="evidence-row" aria-label="데이터 근거 범례">
          <EvidenceBadge kind="REAL">REAL</EvidenceBadge>
          <EvidenceBadge kind="DEMO">DEMO</EvidenceBadge>
          <EvidenceBadge kind="SCENARIO">SCENARIO</EvidenceBadge>
        </div>
      </div>

      <ol className="loop-steps" aria-label="GreenFab Loop 진행 단계">
        {workflowSteps.map(([title, note], index) => {
          const stopped = occurrence === "not-found" && index > 1;
          const state = stopped ? "pending" : index < currentStep ? "complete" : index === currentStep ? "current" : "pending";
          return (
            <li key={title} className={state} aria-current={state === "current" ? "step" : undefined}>
              <b>{state === "complete" ? <Check aria-hidden="true" /> : String(index + 1).padStart(2, "0")}</b>
              <span><strong>{title}</strong><small>{note}</small></span>
            </li>
          );
        })}
      </ol>

      <div className="workspace-layout">
        <div className="workspace-main">
          <section className="case-section detect-confirm-section">
            <div className="section-heading">
              <div><span>01–02 · DETECT &amp; CONFIRM</span><h3>위험 신호와 현장 확인</h3><p>모델 신호를 현장 사실과 분리해 검토합니다.</p></div>
              <EvidenceBadge kind="REAL">REAL · OOF 분석</EvidenceBadge>
            </div>
            <div className="detect-confirm-layout">
              <div className="signal-pane">
                <label className="select-label" htmlFor="loop-risk-case">Golden Demo Case · 고정 연결</label>
                <select id="loop-risk-case" value={selectedRiskId} disabled aria-describedby="golden-case-note">
                  <option value={selectedRisk.id}>{selectedRisk.risk_rank}위 · {selectedRisk.id} · 후향 라벨 {selectedRisk.observed_label}</option>
                </select>
                <small id="golden-case-note" className="select-note">REAL 위험 건과 DEMO 자원을 임의로 재결합하지 않도록 한 건만 명시적으로 연결했습니다.</small>
                <div className="signal-summary">
                  <div><span>상대 위험순위</span><strong>{selectedRisk.risk_rank}위</strong><small>/ {dashboardData.summary.총생산건수}건</small></div>
                  <div><span>상대 위험 백분위</span><strong>{percent(selectedRisk.risk_score)}</strong><small>불량확률 아님</small></div>
                  <div><span>후향 검증 라벨</span><strong className={selectedRisk.observed_label === "불량" ? "danger-text" : ""}>{selectedRisk.observed_label}</strong><small>운영 시점에는 비공개</small></div>
                </div>
                <div className="factor-strip">
                  {selectedRisk.top_factors.slice(0, 3).map((factor) => (
                    <span key={factor.feature}><b>{factor.display_feature}</b><small>{factor.contribution > 0 ? "+" : ""}{factor.contribution.toFixed(3)}</small></span>
                  ))}
                </div>
                <div className="inline-guidance"><CircleAlert aria-hidden="true" /><p><b>해석 기준</b> SHAP은 모델 기여도이며 물리적 원인이나 자원 발생을 뜻하지 않습니다.</p></div>
              </div>
              <div className="confirm-pane">
                <div className="pane-title"><UserCheck aria-hidden="true" /><div><span>HUMAN GATE</span><strong>실제 자원 발생 여부</strong></div></div>
                <p>AI 위험 신호만으로 폐기나 재활용을 결정하지 않습니다. 현장 담당자가 실제 발생 여부를 확인합니다.</p>
                <div className="choice-cards" role="group" aria-label="자원 발생 확인">
                  <button type="button" className={occurrence === "confirmed" ? "active" : ""} onClick={() => chooseOccurrence("confirmed")}>
                    <CheckCircle2 aria-hidden="true" /><span><b>발생 확인</b><small>Passport 생성</small></span>
                  </button>
                  <button type="button" className={occurrence === "not-found" ? "active neutral" : ""} onClick={() => chooseOccurrence("not-found")}>
                    <CircleAlert aria-hidden="true" /><span><b>발생 없음</b><small>모니터링 종료</small></span>
                  </button>
                </div>
                <div className="human-gate"><ShieldCheck aria-hidden="true" /><span><b>Human-in-the-loop</b>추천과 규칙 판정은 검토를 돕고, 상태 확인과 최종 결정은 사람이 수행합니다.</span></div>
              </div>
            </div>
          </section>

          {occurrence === "pending" ? (
            <div className="loop-empty-state"><Clock3 aria-hidden="true" /><b>현장 확인을 기다리고 있습니다.</b><span>발생 여부를 사람이 선택하기 전에는 Passport와 이후 단계가 열리지 않습니다.</span></div>
          ) : occurrence === "not-found" ? (
            <div className="loop-empty-state"><PackageCheck aria-hidden="true" /><b>발생 없음으로 확인했습니다.</b><span>Data Contract에 따라 Passport·Match·Decision·Scenario·Receipt는 모두 null로 종료됩니다.</span></div>
          ) : (
            <>
              <section className="case-section passport-section">
                <div className="section-heading">
                  <div><span>03 · RESOURCE PASSPORT</span><h3>검토 가능한 자원 정보</h3><p>자원의 정체, 물성, 위치와 증거 상태를 한곳에서 확인합니다.</p></div>
                  <EvidenceBadge kind="DEMO">DEMO · 합성 입력</EvidenceBadge>
                </div>
                <div className="passport-banner"><div><span>RESOURCE ID</span><strong>{demoResource.id}</strong></div><div><span>자원명</span><strong>{demoResource.name}</strong></div><small>{dataset.metadata.version}</small></div>
                <div className="passport-groups">
                  <div><span>IDENTITY</span><dl><dt>발생 Case</dt><dd>{selectedRisk.id}</dd><dt>현재 상태</dt><dd>{demoResource.state}</dd></dl></div>
                  <div><span>MATERIAL</span><dl><dt>예상 수량</dt><dd><label className="quantity-input"><input aria-label="예상 자원 수량" type="number" min="1" max="100" value={quantityKg} onChange={(event) => { setQuantityKg(Number(event.target.value)); setReceiptGeneratedAt(null); }} /><span>kg</span></label></dd><dt>분석 상태</dt><dd>{analysisComplete ? "DEMO 성분표 확인" : "분석 필요"}</dd></dl></div>
                  <div><span>LOGISTICS</span><dl><dt>위치</dt><dd><MapPin aria-hidden="true" />{demoResource.location}</dd><dt>활용 가능일</dt><dd>{demoResource.availableOn}</dd></dl></div>
                  <div><span>EVIDENCE</span><dl><dt>입력 주체</dt><dd>현장 담당자 · DEMO</dd><dt>데이터 상태</dt><dd>합성 데모 입력</dd></dl></div>
                </div>
                <div className="resource-description"><FieldLabel kind="DEMO">자원 설명</FieldLabel><p>{demoResource.description}</p></div>
                <label className="analysis-check"><input type="checkbox" checked={analysisComplete} onChange={(event) => { setAnalysisComplete(event.target.checked); setReceiptGeneratedAt(null); }} /><span><b>합성 DEMO 성분표를 확인했습니다.</b><small>현재 상태: {analysisComplete ? "DEMO 성분값 사용" : demoResource.analysisStatus}</small></span></label>
                <div className="inline-guidance"><CircleAlert aria-hidden="true" /><p>SECOM에는 자원명·수량·성분 정보가 없습니다. 이 Passport는 검색 흐름 검증을 위한 합성 입력입니다.</p></div>
              </section>

              <section className="case-section match-section">
                <div className="section-heading">
                  <div><span>04 · AI MATCH</span><h3>추가 검토할 활용처 후보 3건</h3><p>의미 기반 유사도와 1차 규칙 판정을 함께 확인하세요.</p></div>
                  <EvidenceBadge kind="DEMO">{showBaseline ? "DEMO · TF-IDF 기준선" : engineReady ? "DEMO · BGE-M3 실행 결과" : "DEMO · FALLBACK"}</EvidenceBadge>
                </div>
                <div className="match-column-head" aria-hidden="true"><span>후보 활용처</span><span>요구조건</span><span>의미 유사도</span><span>선택</span></div>
                <div className="match-list">
                  {rankedDemands.map(({ rank, score, demand }) => {
                    const rule = ruleStatus(demand, quantityKg, analysisComplete);
                    const distance = "distanceKm" in demand ? demand.distanceKm : null;
                    const range = "quantityRangeKg" in demand ? demand.quantityRangeKg : null;
                    const selected = selectedDemandId === demand.id;
                    return (
                      <button type="button" key={demand.id} className={selected ? "selected" : ""} aria-pressed={selected} onClick={() => { setSelectedDemandId(demand.id); setDecision(null); setDecidedAt(null); setReceiptGeneratedAt(null); }}>
                        <span className="match-rank">{rank}</span>
                        <span className="match-copy"><b>{demand.company}</b><strong>{demand.title}</strong><small>{demand.description}</small></span>
                        <span className="match-requirements"><span><Scale aria-hidden="true" />{range ? `${range[0]}–${range[1]}kg` : "수량 협의"}</span><span><MapPin aria-hidden="true" />{distance !== null ? `${distance}km` : "거리 확인"}</span><i className={`rule-chip ${rule.tone}`}>{rule.label}</i></span>
                        <span className="similarity"><small>성공확률 아님</small><b>{score ? score.toFixed(3) : "—"}</b></span>
                        <span className="match-select">{selected ? <><Check aria-hidden="true" />선택됨</> : "선택"}</span>
                      </button>
                    );
                  })}
                </div>
                <details className="model-comparison">
                  <summary><BrainCircuit aria-hidden="true" />모델 비교와 검증 범위 보기</summary>
                  <div className="metric-compare">
                    <div><span>TF-IDF 기준선</span><strong>Hit@1 {percent(matchResults.metrics.tfidfHitAt1, 1)}</strong><em>Recall@3 {percent(matchResults.metrics.tfidfRecallAt3, 1)}</em></div>
                    <i>VS</i>
                    <div><span>BGE-M3 의미 검색</span><strong>{engineReady ? `Hit@1 ${percent(matchResults.metrics.embeddingHitAt1, 1)}` : "실행 대기"}</strong><em>{engineReady ? `Recall@3 ${percent(matchResults.metrics.embeddingRecallAt3, 1)}` : "—"}</em></div>
                    <small>{matchResults.metrics.resourceCount}개 합성 자원과 {matchResults.metrics.demandCount}개 합성 수요를 대상으로 한 내부 검색 검증입니다.</small>
                  </div>
                  <label className="baseline-toggle"><input type="checkbox" checked={showBaseline} onChange={(event) => changeEngine(event.target.checked)} /><span>현재 후보 목록을 TF-IDF 기준선으로 비교</span></label>
                </details>
                <div className="inline-guidance"><CircleAlert aria-hidden="true" /><p><b>추천 한계</b> 유사도는 성공확률이 아닙니다. 소재 호환성, 안전성, 법적 허용은 별도 검토가 필요합니다.</p></div>
              </section>

              <section className="case-section scenario-section">
                <div className="section-heading">
                  <div><span>06 · ESG SCENARIO</span><h3>승인 기준 전환 후보량</h3><p>사람의 결정과 확인 수량만으로 계산하며 감축량이나 환경성과를 추정하지 않습니다.</p></div>
                  <EvidenceBadge kind="SCENARIO">SCENARIO · 입력값 계산</EvidenceBadge>
                </div>
                <div className="scenario-grid">
                  <div><span>INPUT</span><small>확인 자원 수량</small><strong>{quantityKg}<em>kg</em></strong></div>
                  <div><span>HUMAN DECISION</span><small>최종 결정 상태</small><strong>{decision ? decisionLabels[decision] : "미선택"}</strong></div>
                  <div className="scenario-result"><span>RESULT</span><small>승인 기준 전환 후보량</small><strong>{scenarioDiversionKg === null ? "—" : scenarioDiversionKg}<em>{scenarioDiversionKg === null ? "" : "kg"}</em></strong></div>
                  <div><span>FORMULA</span><small>candidate_diversion_v0.1</small><strong>{decision === "approved" ? "승인 수량" : decision ? "0 kg" : "결정 대기"}</strong></div>
                </div>
                <div className="inline-guidance"><CircleAlert aria-hidden="true" /><p><b>계산 범위</b> `APPROVED`일 때만 확인 수량을 전환 후보량으로 표시합니다. 배출계수는 사용하지 않으며 실제 인계·감축 실적이 아닙니다.</p></div>
              </section>

              <section className="case-section receipt-ledger">
                <div className="section-heading">
                  <div><span>07 · GREEN RECEIPT</span><h3>의사결정 기록 미리보기</h3><p>Data Contract v0.1 구조의 브라우저 다운로드용 의사결정 스냅샷입니다.</p></div>
                  <span className={`decision-status ${decision ?? "hold"}`}>{receiptGeneratedAt ? "초안 생성됨" : canFinalize ? "생성 준비" : "확인 필요"}</span>
                </div>
                <div className="ledger-head"><div><span>RECEIPT ID</span><strong>{receiptId}</strong><small>{receiptGeneratedAt ? "DRAFT JSON · 브라우저 다운로드 완료" : "PREVIEW · 서버에 저장되지 않은 초안"}</small></div><FileCheck2 aria-hidden="true" /></div>
                <div className="ledger-layout">
                  <ol className="receipt-timeline" aria-label="의사결정 기록 진행 상황">
                    <li className="done"><b>14:02</b><span><strong>위험 신호 생성</strong><small>{selectedRisk.id} · 상대 위험순위 {selectedRisk.risk_rank}위</small></span></li>
                    <li className="done"><b>확인</b><span><strong>현장 발생 확인</strong><small>{demoResource.name} · {quantityKg}kg</small></span></li>
                    <li className={analysisComplete ? "done" : "current"}><b>{analysisComplete ? "14:24" : "대기"}</b><span><strong>Resource Passport 검토</strong><small>{analysisComplete ? "성분 분석표 확인" : demoResource.analysisStatus}</small></span></li>
                    <li className="done"><b>14:25</b><span><strong>AI 후보 검색</strong><small>{showBaseline ? "TF-IDF 기준선" : matchResults.model} · {selectedDemand.company}</small></span></li>
                    <li className={decision ? "done" : "pending"}><b>{decision ? "입력" : "대기"}</b><span><strong>{decision ? decisionLabels[decision] : "사람의 결정 대기"}</strong><small>환경·자원관리 담당자 · DEMO</small></span></li>
                    <li className={receiptGeneratedAt ? "done" : canFinalize ? "current" : "pending"}><b>{receiptGeneratedAt ? "완료" : canFinalize ? "준비" : "대기"}</b><span><strong>Green Receipt 초안</strong><small>Data Contract v0.1 JSON</small></span></li>
                  </ol>
                  <dl className="ledger-details">
                    <div><dt>확인 자원</dt><dd>{demoResource.name} · {quantityKg}kg <EvidenceBadge kind="DEMO" /></dd></div>
                    <div><dt>선택 후보</dt><dd>{selectedDemand.company} · {selectedRule.label}</dd></div>
                    <div><dt>사람의 결정</dt><dd>{decision ? decisionLabels[decision] : "미선택"} · 담당자 입력</dd></div>
                    <div><dt>전환 후보량</dt><dd>{scenarioDiversionKg === null ? "—" : `${scenarioDiversionKg}kg`} <EvidenceBadge kind="SCENARIO" /></dd></div>
                    <div className="wide"><dt>결정 근거</dt><dd>{decisionNote || "결정 사유를 입력하세요."}</dd></div>
                  </dl>
                </div>
                <div className="receipt-disclaimer"><ShieldCheck aria-hidden="true" /><span><b>초안 기록 범위</b> 법적 인계서·재활용 적합성 인증서·불변 감사로그가 아닙니다. 현재 MVP는 JSON을 브라우저로 다운로드합니다.</span></div>
              </section>
            </>
          )}
        </div>

        {occurrence === "confirmed" ? <aside className="decision-panel" aria-label="최종 결정 패널">
          <div className="decision-panel-head"><span>05 · HUMAN DECISION</span><h3>담당자 최종 결정</h3><p>AI 추천과 규칙 판정을 확인한 뒤 사람의 판단을 기록합니다.</p></div>
          <div className={`next-action-card ${canFinalize ? "ready" : "attention"}`}><span>{canFinalize ? <CheckCircle2 aria-hidden="true" /> : <CircleAlert aria-hidden="true" />}</span><div><small>다음 행동</small><strong>{nextAction}</strong></div></div>
          <div className="selected-candidate">
            <span>선택한 활용처</span><strong>{selectedDemand.company}</strong><p>{selectedDemand.title}</p><i className={`rule-chip ${selectedRule.tone}`}>{selectedRule.label}</i>
          </div>
          <div className="decision-checklist">
            <span>승인 전 확인</span>
            <label className="checked"><input type="checkbox" checked={occurrence === "confirmed"} readOnly /><span>실제 자원 발생 확인</span></label>
            <label className={quantityOk ? "checked" : "blocked"}><input type="checkbox" checked={quantityOk} readOnly /><span>수량 조건 확인</span></label>
            <label className={analysisComplete ? "checked" : "blocked"}><input type="checkbox" checked={analysisComplete} readOnly /><span>성분 분석 조건 확인</span></label>
            <label className={selectedRule.status === "REVIEW" ? "checked" : "blocked"}><input type="checkbox" checked={selectedRule.status === "REVIEW"} readOnly /><span>결정 규칙상 사람 검토 가능</span></label>
            <label className={aiAcknowledged ? "checked acknowledgement" : "acknowledgement"}><input type="checkbox" checked={aiAcknowledged} onChange={(event) => { setAiAcknowledged(event.target.checked); setReceiptGeneratedAt(null); }} /><span>AI 유사도가 성공확률이 아님을 확인</span></label>
          </div>
          <div className="decision-buttons" role="group" aria-label="최종 검토 결정">
            {(["approved", "hold", "rejected"] as Decision[]).map((value) => (
              <button type="button" key={value} className={`${value} ${decision === value ? "active" : ""}`} aria-pressed={decision === value} onClick={() => { setDecision(value); setDecidedAt(new Date().toISOString()); setReceiptGeneratedAt(null); }}>{decisionLabels[value]}</button>
            ))}
          </div>
          <label className="decision-note"><span>결정 사유</span><textarea value={decisionNote} onChange={(event) => { setDecisionNote(event.target.value); setReceiptGeneratedAt(null); }} rows={5} placeholder="예: 성분표 확인 후 5kg 파일럿 전달을 조건부 승인" /><small>{decisionNote.trim().length}/10자 이상</small></label>
          {!canFinalize && <p className="decision-blocker"><CircleAlert aria-hidden="true" />미완료 확인 항목을 처리해야 기록을 생성할 수 있습니다.</p>}
          <button className="finalize-button" type="button" disabled={!canFinalize} onClick={downloadReceipt}><Download aria-hidden="true" />{receiptGeneratedAt ? "초안 JSON 다시 다운로드" : "Green Receipt 초안 JSON"}<ArrowRight aria-hidden="true" /></button>
          <p className="decision-guardrail">APPROVED는 실제 인계 완료가 아닙니다. 계약, 운반, 법정 처리는 기존 공식 절차를 따릅니다.</p>
        </aside> : <aside className="decision-panel decision-panel-locked" aria-label="잠긴 최종 결정 패널">
          <ShieldCheck aria-hidden="true" />
          <span>05 · HUMAN DECISION</span>
          <h3>현장 확인 후 활성화됩니다</h3>
          <p>자원 발생이 `CONFIRMED`일 때만 후보 검토와 사람의 최종 결정을 진행할 수 있습니다.</p>
        </aside>}
      </div>

      <div className="loop-proof-bar">
        <div><b>REAL</b><span>SECOM 1,567건 OOF 분석</span></div>
        <div><b>DEMO</b><span>{engineReady ? `합성 입력 BGE-M3 ${matchResults.metrics.resourceCount}건 · Top 3 실패 ${bgeFailureCount}건` : "자원·수요·사람 행동"}</span></div>
        <div><b>SCENARIO</b><span>전환 검토량 · 감축 실적 아님</span></div>
      </div>
    </section>
  );
}
