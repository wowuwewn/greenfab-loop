import assert from "node:assert/strict";
import test from "node:test";
import {
  buildLoopContract,
  deriveCandidateStatus,
  SOURCE_TYPES,
  validateLoopContract,
} from "../app/contract-adapter.js";

const confirmedAt = "2026-08-17T10:00:00+09:00";
const decidedAt = "2026-08-17T10:30:00+09:00";

function baseInput() {
  return {
    case_record: {
      case_id: "SECOM-0116",
      risk_rank: 1,
      shap_top_features: [{feature_name: "feature_60", shap_value: 0.31}],
    },
    confirmation: {
      status: "CONFIRMED",
      confirmed_by: "demo_operator",
      confirmed_at: confirmedAt,
    },
    passport: {
      passport_id: "PASSPORT-DEMO-0116",
      description: "DEMO 자원 설명",
      quantity: 12,
      unit: "kg",
      condition: "건조 분말",
      location: "제조동 A",
      composition: null,
    },
    match: {
      model: "Xenova/bge-m3",
      created_at: "2026-08-16T15:56:47.692Z",
      candidates: [
        {
          demand_id: "D01",
          company_name: "제주 세라믹랩",
          demand_description: "무기 충전재 파일럿 원료",
          semantic_similarity: 0.649156,
          rule_check: {
            quantity: true,
            required_info: false,
            location: null,
            missing_fields: ["composition"],
          },
          status: "NEEDS_INFO",
        },
      ],
    },
    decision: null,
    receipt: null,
  };
}

test("PENDING and NOT_CONFIRMED gates null every downstream stage", () => {
  for (const status of ["PENDING", "NOT_CONFIRMED"]) {
    const input = baseInput();
    input.confirmation.status = status;
    input.confirmation.confirmed_by = status === "PENDING" ? null : "demo_operator";
    input.confirmation.confirmed_at = status === "PENDING" ? null : confirmedAt;
    const record = buildLoopContract(input);
    assert.equal(record.resource_confirmation.status, status);
    for (const key of ["resource_passport", "match", "decision", "esg_scenario", "receipt"]) {
      assert.equal(record[key], null, `${key} must be gated by human confirmation`);
    }
  }
});

test("confirmed view state maps to the exact contract envelope", () => {
  const record = buildLoopContract(baseInput());
  assert.deepEqual(Object.keys(record), [
    "case",
    "resource_confirmation",
    "resource_passport",
    "match",
    "decision",
    "esg_scenario",
    "receipt",
  ]);
  assert.equal(record.case.source_type, "REAL");
  assert.equal(record.resource_confirmation.source_type, "DEMO");
  assert.equal(record.resource_passport.source_type, "DEMO");
  assert.equal(record.match.source_type, "DEMO");
  assert.equal(record.decision, null);
  assert.equal(validateLoopContract(record).length, 0);
});

test("human decision creates a contract-safe scenario and referenced receipt", () => {
  const input = baseInput();
  input.passport.composition = "합성 DEMO 성분표";
  input.match.candidates[0].rule_check.required_info = true;
  input.match.candidates[0].rule_check.missing_fields = [];
  input.match.candidates[0].status = "REVIEW";
  input.decision = {
    status: "approved",
    selected_demand_id: "D01",
    reason: "성분표 확인 후 파일럿 전달 승인",
    decided_by: "demo_reviewer",
    decided_at: decidedAt,
  };
  input.receipt = {receipt_id: "GF-DEMO-0116", created_at: decidedAt};

  const record = buildLoopContract(input);
  assert.equal(record.decision.status, "APPROVED");
  assert.equal(record.esg_scenario.source_type, "SCENARIO");
  assert.equal(record.esg_scenario.results.candidate_diversion_quantity, 12);
  assert.equal(record.esg_scenario.factor_source, null);
  assert.equal(record.receipt.case_id, record.case.case_id);
  assert.equal(record.receipt.passport_id, record.resource_passport.passport_id);
  assert.equal(record.receipt.selected_demand_id, record.decision.selected_demand_id);
  assert.equal(record.receipt.handoff_status, "APPROVED");
  assert.equal(validateLoopContract(record).length, 0);
  assert.ok(!JSON.stringify(record).includes("COMPUTED"));
});

test("HOLD does not count unapproved quantity as candidate diversion", () => {
  const input = baseInput();
  input.decision = {
    status: "hold",
    selected_demand_id: "D01",
    reason: "추가 정보 확인 대기",
    decided_by: "demo_reviewer",
    decided_at: decidedAt,
  };
  const record = buildLoopContract(input);
  assert.equal(record.decision.status, "HOLD");
  assert.equal(record.esg_scenario.results.candidate_diversion_quantity, 0);
});

test("deterministic rule status never auto-approves a candidate", () => {
  assert.equal(deriveCandidateStatus({quantity: false, required_info: true, location: null, missing_fields: []}), "RULE_FAIL");
  assert.equal(deriveCandidateStatus({quantity: true, required_info: false, location: null, missing_fields: ["composition"]}), "NEEDS_INFO");
  assert.equal(deriveCandidateStatus({quantity: null, required_info: null, location: null, missing_fields: ["quantity_rule"]}), "NEEDS_INFO");
  assert.equal(deriveCandidateStatus({quantity: true, required_info: true, location: null, missing_fields: []}), "REVIEW");
});

test("runtime validation rejects unsupported provenance labels", () => {
  const record = buildLoopContract(baseInput());
  record.match.source_type = "COMPUTED";
  assert.ok(validateLoopContract(record).some((error) => error.includes("source_type")));
  assert.deepEqual(SOURCE_TYPES, ["REAL", "DEMO", "SCENARIO"]);
});
