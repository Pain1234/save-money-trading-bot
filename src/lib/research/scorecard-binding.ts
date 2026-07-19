import {
  fetchResearchExperiment,
  fetchScorecard,
  fetchScorecards,
  getResearchErrorMessage,
  type ScorecardRecord,
  type ValidationStudyDetail,
  type ValidationStudyOutcome,
} from "@/lib/research-api/client";
import { UNAVAILABLE, type ExecutiveTone } from "@/lib/research/executive-summary";

/** Backend missing-data literal — display as Nicht verfügbar. */
export const BACKEND_NOT_AVAILABLE = "NOT_AVAILABLE";

export type ScorecardBindState =
  | { kind: "empty"; reason: string }
  | { kind: "error"; message: string }
  | { kind: "ready"; scorecard: ScorecardRecord; warnings: string[] };

export interface ScorecardProfileCell {
  id: string;
  label: string;
  value: string;
  detail: string | null;
  tone: ExecutiveTone;
  source: string;
}

export interface ScorecardProfileViewModel {
  cells: ScorecardProfileCell[];
  scorecardId: string;
  status: string;
  experimentId: string;
  runId: string;
  policyVersion: string;
  evidenceIntegrityOk: boolean | null;
  warnings: string[];
  parameterClassification: string | null;
  parameterDetail: string | null;
  confidenceLabel: string | null;
  transitionRiskLabel: string | null;
  transitionDetail: string | null;
  mainWeakness: string | null;
  mainStrength: string | null;
}

/** Map null / empty / backend NOT_AVAILABLE → Nicht verfügbar. */
export function scorecardDisplayValue(
  value: string | number | null | undefined,
): string {
  if (value === null || value === undefined || value === "") {
    return UNAVAILABLE;
  }
  if (String(value) === BACKEND_NOT_AVAILABLE) {
    return UNAVAILABLE;
  }
  return String(value);
}

function asString(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

/** Shared tone mapping for profile strip + analytics panels. */
export function scorecardToneForStatus(raw: string | null): ExecutiveTone {
  if (!raw || raw === BACKEND_NOT_AVAILABLE) return "muted";
  const upper = raw.toUpperCase();
  if (
    upper === "FAIL" ||
    upper === "FAILED" ||
    upper === "INVALID" ||
    upper === "INVALIDATED"
  ) {
    return "danger";
  }
  if (
    upper === "PASS" ||
    upper === "PASSED" ||
    upper === "VALID" ||
    upper === "HIGH" ||
    upper === "BROAD_PLATEAU" ||
    upper === "NARROW_PLATEAU"
  ) {
    return "mint";
  }
  if (
    upper === "NOT_VERIFIABLE" ||
    upper === "INSUFFICIENT_EVIDENCE" ||
    upper === "LOW" ||
    upper === "MEDIUM" ||
    upper === "ISOLATED_PEAK" ||
    upper === "WARNING" ||
    upper === "ELEVATED"
  ) {
    return "warning";
  }
  return "muted";
}

function pickActiveScorecard(items: ScorecardRecord[]): ScorecardRecord | null {
  const active = items.find((item) => item.status === "active");
  return active ?? items[0] ?? null;
}

/** Primary run identity for a Validation Study (snapshot preferred). */
export function studyPrimaryRunId(
  study: Pick<ValidationStudyDetail, "run_id" | "evidence_snapshot">,
): string | null {
  return study.evidence_snapshot?.primary.run_id ?? study.run_id ?? null;
}

/**
 * Prefer scorecards whose run_id matches the study primary run.
 * Never fall back to an additional-run scorecard when primaryRunId is known.
 */
export function pickScorecardForPrimaryRun(
  candidates: ScorecardRecord[],
  primaryRunId: string | null,
): ScorecardRecord | null {
  if (!primaryRunId) return null;
  return pickActiveScorecard(
    candidates.filter((item) => item.run_id === primaryRunId),
  );
}

export type ScorecardTrustResult =
  | { ok: true; warnings: string[] }
  | { ok: false; message: string };

/**
 * Fail-closed for untrusted evidence (integrity fail, pin hash mismatch,
 * or invalidated status). Soft warnings remain empty for ready binds.
 */
export function evaluateScorecardTrust(
  scorecard: ScorecardRecord,
  pinHash?: string | null,
  options?: { requirePinHash?: boolean },
): ScorecardTrustResult {
  if (scorecard.status === "invalidated") {
    return {
      ok: false,
      message: `status=invalidated${
        scorecard.invalidation_reason
          ? `: ${scorecard.invalidation_reason}`
          : ""
      } — Scorecard untrusted`,
    };
  }
  if (scorecard.evidence_integrity && scorecard.evidence_integrity.ok === false) {
    return {
      ok: false,
      message:
        scorecard.evidence_integrity.error ??
        "evidence_integrity.ok=false — Scorecard untrusted",
    };
  }
  if (options?.requirePinHash && !pinHash) {
    return {
      ok: false,
      message:
        "Scorecard ohne evidence_snapshot Pin-Hash — ungepinnt, fail-closed",
    };
  }
  if (
    pinHash &&
    scorecard.evidence_content_hash &&
    pinHash !== scorecard.evidence_content_hash
  ) {
    return {
      ok: false,
      message: "pinned scorecard content_hash mismatch — Evidence untrusted",
    };
  }
  return { ok: true, warnings: [] };
}

function bindTrustedScorecard(
  scorecard: ScorecardRecord,
  pinHash?: string | null,
  options?: { requirePinHash?: boolean },
): ScorecardBindState {
  const trust = evaluateScorecardTrust(scorecard, pinHash, options);
  if (!trust.ok) {
    return { kind: "error", message: trust.message };
  }
  return { kind: "ready", scorecard, warnings: trust.warnings };
}

export async function loadScorecardForRun(
  runId: string | null | undefined,
): Promise<ScorecardBindState> {
  if (!runId) {
    return {
      kind: "empty",
      reason: "Kein run_id — Scorecard kann nicht geladen werden",
    };
  }
  try {
    const list = await fetchScorecards({ run_id: runId });
    const scorecard = pickActiveScorecard(list.items);
    if (!scorecard) {
      return {
        kind: "empty",
        reason: `Keine Scorecards für run_id=${runId}`,
      };
    }
    // Experiment/strategy path: integrity + active status; no study pin.
    return bindTrustedScorecard(scorecard);
  } catch (error) {
    return { kind: "error", message: getResearchErrorMessage(error) };
  }
}

function studyScorecardCandidateIds(study: ValidationStudyDetail): string[] {
  const pinned = study.evidence_snapshot?.scorecards ?? [];
  const fromStudy =
    study.scorecard_ids && study.scorecard_ids.length > 0
      ? study.scorecard_ids
      : pinned.map((p) => p.scorecard_id);
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const id of fromStudy) {
    if (!id || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }
  return ids;
}

/**
 * Pure study bind resolution (no network). Never falls back to unpinned
 * registry scorecards — only primary-run + snapshot-pinned candidates.
 */
export function resolveStudyScorecardBind(
  fetched: ScorecardRecord[],
  study: Pick<
    ValidationStudyDetail,
    "run_id" | "evidence_snapshot" | "scorecard_ids"
  >,
  fetchErrors: string[] = [],
): ScorecardBindState {
  const primaryRunId = studyPrimaryRunId(study);
  const pinned = study.evidence_snapshot?.scorecards ?? [];
  const ids = studyScorecardCandidateIds(study as ValidationStudyDetail);

  if (ids.length === 0) {
    return {
      kind: "empty",
      reason:
        "Keine Scorecard an Study gepinnt (scorecard_ids / evidence_snapshot.scorecards) — Registry-Fallback unterdrückt",
    };
  }

  const allowedIds = new Set(ids);
  const pinnedCandidates = fetched.filter((item) =>
    allowedIds.has(item.scorecard_id),
  );
  const primaryMatch = pickScorecardForPrimaryRun(
    pinnedCandidates,
    primaryRunId,
  );
  if (!primaryMatch) {
    if (fetchErrors.length > 0 && fetched.length === 0) {
      return {
        kind: "error",
        message: fetchErrors[0] ?? "Scorecard-Fetch fehlgeschlagen",
      };
    }
    return {
      kind: "empty",
      reason:
        "Keine gepinnte Scorecard für den Primary-Run — Additional-Run-Pins und ungepinnte Registry-Treffer werden nicht als Study-Profil genutzt",
    };
  }

  const pin = pinned.find((p) => p.scorecard_id === primaryMatch.scorecard_id);
  return bindTrustedScorecard(primaryMatch, pin?.content_hash ?? null, {
    // Study profile requires a sealed snapshot pin — never bind bare ids.
    requirePinHash: true,
  });
}

export async function loadScorecardForStudy(
  study: ValidationStudyDetail,
): Promise<ScorecardBindState> {
  const ids = studyScorecardCandidateIds(study);
  if (ids.length === 0) {
    return resolveStudyScorecardBind([], study);
  }

  const fetched: ScorecardRecord[] = [];
  const fetchErrors: string[] = [];
  const results = await Promise.allSettled(ids.map((id) => fetchScorecard(id)));
  for (const result of results) {
    if (result.status === "fulfilled") {
      fetched.push(result.value);
    } else {
      fetchErrors.push(getResearchErrorMessage(result.reason));
    }
  }

  return resolveStudyScorecardBind(fetched, study, fetchErrors);
}

export async function loadScorecardForExperiment(
  runId: string | null | undefined,
): Promise<ScorecardBindState> {
  return loadScorecardForRun(runId);
}

/** Strategy detail: resolve via last experiment → run_id → scorecards. */
export async function loadScorecardForStrategy(lastExperimentId: string | null | undefined): Promise<ScorecardBindState> {
  if (!lastExperimentId) {
    return {
      kind: "empty",
      reason: "Kein letztes Experiment — Scorecard nicht gebunden",
    };
  }
  try {
    const detail = await fetchResearchExperiment(lastExperimentId);
    const runId = detail.summary?.run_id ?? detail.metadata?.run_id ?? null;
    return loadScorecardForRun(runId);
  } catch (error) {
    return { kind: "error", message: getResearchErrorMessage(error) };
  }
}

function transitionRiskLabel(
  transitionRisk: Record<string, unknown> | null | undefined,
): string | null {
  if (!transitionRisk) return null;
  return asString(transitionRisk.risk_label);
}

function transitionRiskDetail(
  transitionRisk: Record<string, unknown> | null | undefined,
): string | null {
  if (!transitionRisk) return null;
  const count = transitionRisk.transition_count;
  const parts: string[] = [];
  if (count !== undefined && count !== null) {
    parts.push(`transitions=${String(count)}`);
  }
  const mae = asString(transitionRisk.mae);
  if (mae && mae !== BACKEND_NOT_AVAILABLE) {
    parts.push(`mae=${mae}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

function parameterClassification(
  area: Record<string, unknown> | null | undefined,
): string | null {
  if (!area) return null;
  const status = asString(area.status);
  if (status === BACKEND_NOT_AVAILABLE) return BACKEND_NOT_AVAILABLE;
  return asString(area.classification) ?? status;
}

function parameterDetail(
  area: Record<string, unknown> | null | undefined,
): string | null {
  if (!area) return null;
  const reason = asString(area.classification_reason) ?? asString(area.limitation);
  const id = asString(area.parameter_area_id);
  if (reason && id) return `${reason} · ${id}`;
  return reason ?? id;
}

export function buildScorecardProfileView(
  scorecard: ScorecardRecord,
  options?: {
    warnings?: string[];
    finalDecision?: {
      outcome: ValidationStudyOutcome | string;
      detail?: string | null;
    } | null;
  },
): ScorecardProfileViewModel {
  const profile = scorecard.global_profile ?? {};
  const gates = profile.gates ?? {};
  const quality = profile.quality ?? {};
  const confidence = profile.confidence ?? {};
  const behaviour = profile.behaviour ?? {};
  const transitionRisk =
    behaviour.transition_risk && typeof behaviour.transition_risk === "object"
      ? (behaviour.transition_risk as Record<string, unknown>)
      : null;
  const parameterArea =
    profile.parameter_area && typeof profile.parameter_area === "object"
      ? (profile.parameter_area as Record<string, unknown>)
      : null;

  const integrity = asString(gates.integrity_status);
  const overall = asString(gates.overall_status);
  const worstRegime = asString(quality.worst_regime);
  const tRisk = transitionRiskLabel(transitionRisk);
  const paramClass = parameterClassification(parameterArea);
  const confLabel = asString(confidence.overall_label);
  const weakness = asString(behaviour.main_weakness);
  const strength = asString(behaviour.main_strength);

  const costLimitation = scorecard.limitations?.find(
    (lim) => lim.code === "cost_stress" || lim.code.includes("cost"),
  );

  const cells: ScorecardProfileCell[] = [
    {
      id: "integrity",
      label: "Integrity",
      value: scorecardDisplayValue(integrity),
      detail: gates.gate_run_id
        ? `gate_run_id=${gates.gate_run_id}`
        : "Kein gate_run_id am Scorecard",
      tone: scorecardToneForStatus(integrity),
      source: "global_profile.gates.integrity_status",
    },
    {
      id: "critical-gates",
      label: "Critical Gates",
      value: scorecardDisplayValue(overall),
      detail: gates.gate_run_id
        ? `overall_status · ${gates.gate_run_id}`
        : "overall_status",
      tone: scorecardToneForStatus(overall),
      source: "global_profile.gates.overall_status",
    },
    {
      id: "worst-regime",
      label: "Worst Regime",
      value: scorecardDisplayValue(worstRegime),
      detail: quality.strongest_regime
        ? `strongest=${scorecardDisplayValue(asString(quality.strongest_regime))}`
        : null,
      tone: scorecardToneForStatus(worstRegime),
      source: "global_profile.quality.worst_regime",
    },
    {
      id: "worst-transition",
      label: "Worst Transition",
      value: scorecardDisplayValue(tRisk),
      detail: transitionRiskDetail(transitionRisk),
      tone: scorecardToneForStatus(tRisk),
      source: "global_profile.behaviour.transition_risk.risk_label",
    },
    {
      id: "cost-stress",
      label: "Cost Stress",
      value: costLimitation
        ? scorecardDisplayValue(costLimitation.status)
        : UNAVAILABLE,
      detail: costLimitation
        ? costLimitation.detail
        : "Nicht in Layer-5 global_profile — Cost-Stress nur als Robustness-Job",
      tone: costLimitation
        ? scorecardToneForStatus(costLimitation.status)
        : "muted",
      source: "limitations[cost*] | absent",
    },
    {
      id: "parameter-area",
      label: "Parameter Area",
      value: scorecardDisplayValue(paramClass),
      detail: parameterDetail(parameterArea),
      tone: scorecardToneForStatus(paramClass),
      source: "global_profile.parameter_area.classification",
    },
    {
      id: "evidence-confidence",
      label: "Evidence Confidence",
      value: scorecardDisplayValue(confLabel),
      detail: confidence.source
        ? `source=${String(confidence.source)}`
        : null,
      tone: scorecardToneForStatus(confLabel),
      source: "global_profile.confidence.overall_label",
    },
    {
      id: "main-weakness",
      label: "Main Weakness",
      value: scorecardDisplayValue(weakness),
      detail: strength
        ? `strength=${scorecardDisplayValue(strength)}`
        : null,
      tone: weakness && weakness !== BACKEND_NOT_AVAILABLE ? "warning" : "muted",
      source: "global_profile.behaviour.main_weakness",
    },
    {
      id: "final-decision",
      label: "Final Human Decision",
      value: options?.finalDecision
        ? String(options.finalDecision.outcome)
        : UNAVAILABLE,
      detail: options?.finalDecision?.detail ??
        (options?.finalDecision
          ? null
          : "Nur an Validation Study — Scorecard promotion_action=none"),
      tone: options?.finalDecision
        ? options.finalDecision.outcome === "accept"
          ? "mint"
          : options.finalDecision.outcome === "reject"
            ? "danger"
            : "warning"
        : "muted",
      source: "validation study decision | none",
    },
  ];

  return {
    cells,
    scorecardId: scorecard.scorecard_id,
    status: String(scorecard.status),
    experimentId: scorecard.experiment_id,
    runId: scorecard.run_id,
    policyVersion: scorecard.policy_version,
    evidenceIntegrityOk: scorecard.evidence_integrity
      ? scorecard.evidence_integrity.ok
      : null,
    warnings: options?.warnings ?? [],
    parameterClassification: paramClass,
    parameterDetail: parameterDetail(parameterArea),
    confidenceLabel: confLabel,
    transitionRiskLabel: tRisk,
    transitionDetail: transitionRiskDetail(transitionRisk),
    mainWeakness: weakness,
    mainStrength: strength,
  };
}
