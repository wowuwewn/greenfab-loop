// @ts-check

/** @typedef {"REAL" | "DEMO" | "SCENARIO"} SourceType */
/** @typedef {"PENDING" | "CONFIRMED" | "NOT_CONFIRMED"} ConfirmationStatus */
/** @typedef {"approved" | "hold" | "rejected"} UiDecisionStatus */
/** @typedef {"APPROVED" | "HOLD" | "REJECTED"} DecisionStatus */
/** @typedef {"REVIEW" | "NEEDS_INFO" | "RULE_FAIL"} CandidateStatus */

/**
 * @typedef {{
 *   quantity: boolean | null,
 *   required_info: boolean | null,
 *   location: boolean | null,
 *   missing_fields: string[] | null
 * }} RuleCheck
 */

/**
 * @typedef {{
 *   demand_id: string,
 *   company_name: string,
 *   demand_description: string,
 *   semantic_similarity: number | null,
 *   rule_check: RuleCheck,
 *   status: CandidateStatus
 * }} MatchCandidate
 */

/**
 * @typedef {{
 *   case: {
 *     case_id: string,
 *     risk_rank: number | null,
 *     shap_top_features: Array<{feature_name: string, shap_value: number}> | null,
 *     source_type: "REAL" | "DEMO"
 *   },
 *   resource_confirmation: {
 *     status: ConfirmationStatus,
 *     confirmed_by: string | null,
 *     confirmed_at: string | null,
 *     source_type: "REAL" | "DEMO"
 *   },
 *   resource_passport: null | {
 *     passport_id: string,
 *     description: string | null,
 *     quantity: number | null,
 *     unit: string | null,
 *     condition: string | null,
 *     location: string | null,
 *     composition: string | null,
 *     source_type: "DEMO"
 *   },
 *   match: null | {
 *     model: string,
 *     created_at: string | null,
 *     source_type: "DEMO",
 *     candidates: MatchCandidate[]
 *   },
 *   decision: null | {
 *     status: DecisionStatus,
 *     selected_demand_id: string | null,
 *     reason: string | null,
 *     decided_by: string,
 *     decided_at: string
 *   },
 *   esg_scenario: null | {
 *     source_type: "SCENARIO",
 *     inputs: {
 *       resource_quantity: number | null,
 *       unit: string | null,
 *       decision_status: DecisionStatus
 *     },
 *     results: {
 *       candidate_diversion_quantity: number,
 *       unit: string | null
 *     },
 *     formula_version: string,
 *     factor_source: null
 *   },
 *   receipt: null | {
 *     receipt_id: string,
 *     case_id: string,
 *     passport_id: string,
 *     selected_demand_id: string | null,
 *     decision_status: DecisionStatus,
 *     handoff_status: "APPROVED" | "RESOURCE_CONFIRMED",
 *     created_at: string
 *   }
 * }} LoopContract
 */

/**
 * @typedef {{
 *   case_record: Omit<LoopContract["case"], "source_type">,
 *   confirmation: Omit<LoopContract["resource_confirmation"], "source_type">,
 *   passport: null | Omit<NonNullable<LoopContract["resource_passport"]>, "source_type">,
 *   match: null | Omit<NonNullable<LoopContract["match"]>, "source_type">,
 *   decision: null | {
 *     status: UiDecisionStatus,
 *     selected_demand_id: string | null,
 *     reason: string | null,
 *     decided_by: string,
 *     decided_at: string
 *   },
 *   receipt: null | {receipt_id: string, created_at: string}
 * }} ContractAdapterInput
 */

export const SOURCE_TYPES = Object.freeze(["REAL", "DEMO", "SCENARIO"]);

/**
 * Deterministic rules only produce a review state. They never approve a candidate.
 * Missing rule definitions or required information must not pass silently.
 * @param {RuleCheck} ruleCheck
 * @returns {CandidateStatus}
 */
export function deriveCandidateStatus(ruleCheck) {
  if (ruleCheck.quantity === false || ruleCheck.location === false) return "RULE_FAIL";
  if (ruleCheck.required_info !== true || ruleCheck.quantity === null) return "NEEDS_INFO";
  return "REVIEW";
}

/** @param {UiDecisionStatus} status @returns {DecisionStatus} */
export function toContractDecisionStatus(status) {
  return /** @type {DecisionStatus} */ (status.toUpperCase());
}

/**
 * Convert the frontend view state to the exact Data Contract v0.1 envelope.
 * Later stages are forcibly nulled when the human confirmation gate is not CONFIRMED.
 * @param {ContractAdapterInput} input
 * @returns {LoopContract}
 */
export function buildLoopContract(input) {
  /** @type {LoopContract} */
  const record = {
    case: {...input.case_record, source_type: "REAL"},
    resource_confirmation: {...input.confirmation, source_type: "DEMO"},
    resource_passport: null,
    match: null,
    decision: null,
    esg_scenario: null,
    receipt: null,
  };

  if (input.confirmation.status !== "CONFIRMED") {
    assertValidLoopContract(record);
    return record;
  }

  if (input.passport) record.resource_passport = {...input.passport, source_type: "DEMO"};
  if (input.match) record.match = {...input.match, source_type: "DEMO"};

  if (input.decision) {
    const decisionStatus = toContractDecisionStatus(input.decision.status);
    record.decision = {...input.decision, status: decisionStatus};
    record.esg_scenario = {
      source_type: "SCENARIO",
      inputs: {
        resource_quantity: record.resource_passport?.quantity ?? null,
        unit: record.resource_passport?.unit ?? null,
        decision_status: decisionStatus,
      },
      results: {
        candidate_diversion_quantity:
          decisionStatus === "APPROVED" ? (record.resource_passport?.quantity ?? 0) : 0,
        unit: record.resource_passport?.unit ?? null,
      },
      formula_version: "candidate_diversion_v0.1",
      factor_source: null,
    };

    if (input.receipt && record.resource_passport) {
      record.receipt = {
        receipt_id: input.receipt.receipt_id,
        case_id: record.case.case_id,
        passport_id: record.resource_passport.passport_id,
        selected_demand_id: record.decision.selected_demand_id,
        decision_status: decisionStatus,
        handoff_status: decisionStatus === "APPROVED" ? "APPROVED" : "RESOURCE_CONFIRMED",
        created_at: input.receipt.created_at,
      };
    }
  }

  assertValidLoopContract(record);
  return record;
}

/**
 * Lightweight runtime guard used by the download path and unit tests.
 * @param {LoopContract} record
 * @returns {string[]}
 */
export function validateLoopContract(record) {
  /** @type {string[]} */
  const errors = [];
  const expectedTopLevel = [
    "case",
    "resource_confirmation",
    "resource_passport",
    "match",
    "decision",
    "esg_scenario",
    "receipt",
  ];
  if (JSON.stringify(Object.keys(record)) !== JSON.stringify(expectedTopLevel)) {
    errors.push("top-level keys must match Data Contract v0.1");
  }

  /** @param {unknown} value @param {string} path */
  const inspect = (value, path) => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) {
      value.forEach((child, index) => inspect(child, `${path}[${index}]`));
      return;
    }
    for (const [key, child] of Object.entries(value)) {
      const childPath = `${path}.${key}`;
      if (!/^[a-z][a-z0-9_]*$/.test(key)) errors.push(`${childPath} is not snake_case`);
      if (key === "source_type" && !SOURCE_TYPES.includes(/** @type {SourceType} */ (child))) {
        errors.push(`${childPath} has an unsupported source_type`);
      }
      inspect(child, childPath);
    }
  };
  inspect(record, "record");

  const isoFields = [
    record.resource_confirmation.confirmed_at,
    record.match?.created_at ?? null,
    record.decision?.decided_at ?? null,
    record.receipt?.created_at ?? null,
  ];
  for (const value of isoFields) {
    if (value !== null && Number.isNaN(Date.parse(value))) errors.push(`${value} is not an ISO 8601 timestamp`);
  }

  if (record.resource_confirmation.status !== "CONFIRMED") {
    for (const key of ["resource_passport", "match", "decision", "esg_scenario", "receipt"]) {
      if (record[/** @type {keyof LoopContract} */ (key)] !== null) errors.push(`${key} must be null before confirmation`);
    }
  }
  if (record.match?.source_type !== undefined && record.match.source_type !== "DEMO") {
    errors.push("match.source_type must remain DEMO for synthetic inputs");
  }
  if (record.esg_scenario?.source_type !== undefined && record.esg_scenario.source_type !== "SCENARIO") {
    errors.push("esg_scenario.source_type must be SCENARIO");
  }
  if (record.receipt) {
    if (!record.decision || !record.resource_passport) errors.push("receipt requires decision and passport");
    if (record.receipt.case_id !== record.case.case_id) errors.push("receipt.case_id reference mismatch");
    if (record.resource_passport && record.receipt.passport_id !== record.resource_passport.passport_id) {
      errors.push("receipt.passport_id reference mismatch");
    }
  }
  return errors;
}

/** @param {LoopContract} record */
export function assertValidLoopContract(record) {
  const errors = validateLoopContract(record);
  if (errors.length) throw new Error(`Invalid GreenFab Loop contract: ${errors.join("; ")}`);
}
