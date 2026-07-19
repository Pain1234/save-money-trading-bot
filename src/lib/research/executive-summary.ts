import type {
  GateRunRecord,
  ResearchExperimentSummary,
  ResearchOverview,
  RobustnessJobSummary,
  ValidationStudyDetail,
} from "@/lib/research-api/client";
import {
  buildScorecardProfileView,
  classifyStudyScorecardPin,
  SCORECARD_PIN_STATUS,
  type ScorecardBindState,
  type ScorecardPinClassification,
} from "@/lib/research/scorecard-binding";
import { UNAVAILABLE, type ExecutiveTone } from "@/lib/research/labels";

export { UNAVAILABLE, type ExecutiveTone } from "@/lib/research/labels";

export interface ExecutiveCell {
  id: string;
  label: string;
  value: string;
  detail: string | null;
  tone: ExecutiveTone;
  href: string | null;
  source: string;
}

export interface ExecutiveEvidenceAnchor {
  studyId: string;
  studyName: string;
  experimentId: string;
  runId: string | null;
  strategyId: string | null;
  strategyVersion: string | null;
  gateRunIds: string[];
  robustnessIds: string[];
  scorecardId?: string | null;
}

export interface ExecutiveSummary {
  cells: ExecutiveCell[];
  /** Single Validation Study that all bound cells refer to — or null. */
  evidence: ExecutiveEvidenceAnchor | null;
  strategyId: string | null;
  strategyVersion: string | null;
  freezeLabel: string;
  freezeDetail: string;
  /** Pin classification for Overview chrome (#358). */
  pin: ScorecardPinClassification;
}

function byNewestCreated<T extends { created_at: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

/**
 * One evidence identity for the strip: prefer newest decided study, else newest open.
 * Gate / Decision / Strategy / Integrity / robustness inventory must all bind here.
 */
export function selectEvidenceStudy(
  studies: ValidationStudyDetail[],
): ValidationStudyDetail | null {
  const decided = byNewestCreated(
    studies.filter((s) => s.status === "decided" && s.decision != null),
  );
  if (decided[0]) return decided[0];
  return byNewestCreated(studies.filter((s) => s.status === "open"))[0] ?? null;
}

export function toEvidenceAnchor(
  study: ValidationStudyDetail,
): ExecutiveEvidenceAnchor {
  const snapshot = study.evidence_snapshot;
  const gateRunIds =
    snapshot && snapshot.gates.length > 0
      ? snapshot.gates.map((g) => g.gate_run_id)
      : [...study.gate_run_ids];
  const robustnessIds =
    snapshot && snapshot.robustness.length > 0
      ? snapshot.robustness.map((r) => r.robustness_id)
      : [...study.robustness_ids];
  const experimentId = snapshot?.primary.experiment_id ?? study.experiment_id;
  const runId = snapshot?.primary.run_id ?? study.run_id;

  return {
    studyId: study.study_id,
    studyName: study.name,
    experimentId,
    runId,
    strategyId: study.strategy_id,
    strategyVersion: study.strategy_version,
    gateRunIds,
    robustnessIds,
  };
}

function jobCounts(jobs: RobustnessJobSummary[]) {
  const complete = jobs.filter(
    (j) => j.status === "completed" || j.status === "complete",
  ).length;
  const failed = jobs.filter((j) => j.status === "failed").length;
  const running = jobs.filter(
    (j) => j.status === "running" || j.status === "queued",
  ).length;
  return { total: jobs.length, complete, failed, running };
}

/** Robustness jobs pinned by study.robustness_ids only — no experiment fallback. */
export function filterJobsForEvidence(
  jobs: RobustnessJobSummary[],
  evidence: ExecutiveEvidenceAnchor,
  testType: string,
): RobustnessJobSummary[] {
  if (evidence.robustnessIds.length === 0) return [];
  const pinned = new Set(evidence.robustnessIds);
  return jobs.filter(
    (j) => j.test_type === testType && pinned.has(j.robustness_id),
  );
}

/**
 * Active gate runs pinned by study.gate_run_ids only.
 * Never widen to experiment_id/run_id — that leaks later unpinned evaluations.
 */
export function filterGatesForEvidence(
  gateRuns: GateRunRecord[],
  evidence: ExecutiveEvidenceAnchor,
): GateRunRecord[] {
  if (evidence.gateRunIds.length === 0) return [];
  const pinnedIds = new Set(evidence.gateRunIds);
  return gateRuns.filter(
    (g) => g.status === "active" && pinnedIds.has(g.gate_run_id),
  );
}

/**
 * Prefer gates already hydrated on the Validation Study detail.
 * Fall back to global list filtered by pinned gate_run_ids only.
 * Never widen to experiment_id / run_id.
 */
export function resolveBoundGates(
  study: ValidationStudyDetail,
  gateRuns: GateRunRecord[],
): GateRunRecord[] {
  const evidence = toEvidenceAnchor(study);
  if (evidence.gateRunIds.length === 0) return [];
  const pinned = new Set(evidence.gateRunIds);
  if (study.gates.length > 0) {
    return study.gates.filter(
      (g) => g.status === "active" && pinned.has(g.gate_run_id),
    );
  }
  return filterGatesForEvidence(gateRuns, evidence);
}

function findPinnedExperiment(
  experiments: ResearchExperimentSummary[],
  evidence: ExecutiveEvidenceAnchor,
): ResearchExperimentSummary | null {
  if (evidence.runId) {
    // Exact run pin — never fall back to a different run of the same experiment.
    return experiments.find((e) => e.run_id === evidence.runId) ?? null;
  }
  return (
    experiments.find((e) => e.experiment_id === evidence.experimentId) ?? null
  );
}

/**
 * Integrity is scoped to the evidence-pinned experiment only.
 * Never roll up unrelated recent experiments into VALID/INVALID.
 */
function integrityCellForEvidence(
  experiments: ResearchExperimentSummary[],
  evidence: ExecutiveEvidenceAnchor | null,
): ExecutiveCell {
  if (!evidence) {
    return {
      id: "integrity",
      label: "Integrity",
      value: UNAVAILABLE,
      detail: "Kein Validation-Study-Anker — keine gebundene Integrity-Aussage",
      tone: "muted",
      href: "/dashboard/research/validation",
      source: "evidence.anchor",
    };
  }

  const pinned = findPinnedExperiment(experiments, evidence);
  if (!pinned) {
    return {
      id: "integrity",
      label: "Integrity",
      value: "NOT_VERIFIABLE",
      detail: `Primary ${evidence.experimentId} nicht in Overview-Recent — Registry-Integrity nicht prüfbar`,
      tone: "warning",
      href: `/dashboard/research/experiments/${encodeURIComponent(evidence.experimentId)}`,
      source: "experiment.integrity_ok (pinned)",
    };
  }

  if (pinned.integrity_ok === false) {
    return {
      id: "integrity",
      label: "Integrity",
      value: "INVALID",
      detail: `Pinned ${pinned.experiment_id}${pinned.integrity_error ? `: ${pinned.integrity_error}` : ""}`,
      tone: "danger",
      href: `/dashboard/research/experiments/${encodeURIComponent(pinned.experiment_id)}`,
      source: "experiment.integrity_ok (pinned)",
    };
  }

  return {
    id: "integrity",
    label: "Integrity",
    value: "VALID",
    detail: `Nur gepinnter Run ${pinned.run_id} · Study ${evidence.studyId}`,
    tone: "mint",
    href: `/dashboard/research/experiments/${encodeURIComponent(pinned.experiment_id)}`,
    source: "experiment.integrity_ok (pinned)",
  };
}

function criticalGatesCellForEvidence(
  gateRuns: GateRunRecord[],
  focus: ValidationStudyDetail | null,
): ExecutiveCell {
  if (!focus) {
    return {
      id: "critical-gates",
      label: "Critical Gates",
      value: UNAVAILABLE,
      detail: "Kein Validation-Study-Anker — Gates nicht aggregiert",
      tone: "muted",
      href: "/dashboard/research/validation",
      source: "evidence.anchor",
    };
  }

  const evidence = toEvidenceAnchor(focus);
  const bound = resolveBoundGates(focus, gateRuns);
  if (bound.length === 0) {
    return {
      id: "critical-gates",
      label: "Critical Gates",
      value: UNAVAILABLE,
      detail: `Study ${evidence.studyId}: keine gepinnten aktiven Gate-Runs`,
      tone: "muted",
      href: `/dashboard/research/validation/${encodeURIComponent(evidence.studyId)}`,
      source: "gates (study-bound pins)",
    };
  }

  const pass = bound.filter((g) => g.overall_status === "pass").length;
  const fail = bound.filter((g) => g.overall_status === "fail").length;
  const latest = [...bound].sort((a, b) =>
    b.evaluated_at.localeCompare(a.evaluated_at),
  )[0]!;

  if (fail > 0) {
    return {
      id: "critical-gates",
      label: "Critical Gates",
      value: "FAIL",
      detail: `${fail} fail / ${pass} pass · Study ${evidence.studyId}`,
      tone: "danger",
      href: `/dashboard/research/validation/${encodeURIComponent(evidence.studyId)}`,
      source: "gates.overall_status (study-bound pins)",
    };
  }

  return {
    id: "critical-gates",
    label: "Critical Gates",
    value: "PASS",
    detail: `${pass} pass · policy ${latest.policy_version} · Study ${evidence.studyId}`,
    tone: "mint",
    href: `/dashboard/research/validation/${encodeURIComponent(evidence.studyId)}`,
    source: "gates.overall_status (study-bound pins)",
  };
}

function unavailableScorecardCell(
  id: string,
  label: string,
  reason: string,
  href: string | null = null,
): ExecutiveCell {
  return {
    id,
    label,
    value: UNAVAILABLE,
    detail: reason,
    tone: "muted",
    href,
    source: "scorecard (#291/#295)",
  };
}

function robustnessInventoryCell(
  id: string,
  label: string,
  jobs: RobustnessJobSummary[],
  testType: string,
  evidence: ExecutiveEvidenceAnchor | null,
): ExecutiveCell {
  if (!evidence) {
    return unavailableScorecardCell(
      id,
      label,
      "Kein Validation-Study-Anker — Robustheit nicht inventarisiert",
      "/dashboard/research/robustness",
    );
  }

  const bound = filterJobsForEvidence(jobs, evidence, testType);
  const counts = jobCounts(bound);
  if (counts.total === 0) {
    return unavailableScorecardCell(
      id,
      label,
      `Scorecard fehlt · Study ${evidence.studyId}: keine ${testType}-Jobs`,
      `/dashboard/research/validation/${encodeURIComponent(evidence.studyId)}`,
    );
  }

  return {
    id,
    label,
    value: UNAVAILABLE,
    detail: `Scorecard fehlt · Study ${evidence.studyId}: Jobs ${counts.complete} complete / ${counts.failed} failed / ${counts.running} running`,
    tone: "muted",
    href: `/dashboard/research/validation/${encodeURIComponent(evidence.studyId)}`,
    source: `robustness.test_type=${testType} (study-bound)`,
  };
}

function finalDecisionCell(
  study: ValidationStudyDetail | null,
): ExecutiveCell {
  if (!study) {
    return {
      id: "final-decision",
      label: "Final Human Decision",
      value: UNAVAILABLE,
      detail: "Keine Validation Studies",
      tone: "muted",
      href: "/dashboard/research/validation",
      source: "validation.decision",
    };
  }

  const href = `/dashboard/research/validation/${encodeURIComponent(study.study_id)}`;

  if (study.status === "decided" && study.decision != null) {
    const outcome = study.decision.outcome;
    const tone: ExecutiveTone =
      outcome === "accept"
        ? "mint"
        : outcome === "reject"
          ? "danger"
          : "warning";
    return {
      id: "final-decision",
      label: "Final Human Decision",
      value: outcome.toUpperCase(),
      detail: `${study.name} · ${study.study_id}`,
      tone,
      href,
      source: "validation.decision.outcome (anchor)",
    };
  }

  return {
    id: "final-decision",
    label: "Final Human Decision",
    value: "pending",
    detail: `${study.name} · ${study.study_id}`,
    tone: "warning",
    href,
    source: "validation.status (anchor)",
  };
}

function profileCellToExecutive(
  cell: {
    id: string;
    label: string;
    value: string;
    detail: string | null;
    tone: ExecutiveTone;
    source: string;
  },
  href: string | null,
): ExecutiveCell {
  return {
    id: cell.id,
    label: cell.label,
    value: cell.value,
    detail: cell.detail,
    tone: cell.tone,
    href,
    source: cell.source,
  };
}

/**
 * Gate-first executive summary (#299 + #358 pinned scorecard).
 * READY pin → profile fields from sealed scorecard API only.
 * Legacy / unpinned → honest pin status; never latest-scorecard fallback.
 */
export function buildExecutiveSummary(input: {
  overview: ResearchOverview;
  gateRuns: GateRunRecord[];
  studies: ValidationStudyDetail[];
  robustnessJobs: RobustnessJobSummary[];
  /** Pinned study scorecard bind — never a registry "latest" pick. */
  scorecardBind?: ScorecardBindState | null;
}): ExecutiveSummary {
  const { overview, gateRuns, studies, robustnessJobs, scorecardBind } = input;
  const focus = selectEvidenceStudy(studies);
  const evidence = focus ? toEvidenceAnchor(focus) : null;
  const pin = classifyStudyScorecardPin(scorecardBind ?? null, focus);
  const studyHref = pin.studyHref;

  if (
    scorecardBind?.kind === "ready" &&
    pin.status === SCORECARD_PIN_STATUS.READY
  ) {
    const profile = buildScorecardProfileView(scorecardBind.scorecard, {
      warnings: scorecardBind.warnings,
      finalDecision:
        focus?.decision != null
          ? {
              outcome: focus.decision.outcome,
              detail: `${focus.decision.decided_by} · ${focus.decision.decided_at}`,
            }
          : null,
    });
    const byId = Object.fromEntries(profile.cells.map((c) => [c.id, c]));
    if (evidence) {
      evidence.scorecardId = profile.scorecardId;
    }

    const fallback = (
      id: string,
      label: string,
    ): {
      id: string;
      label: string;
      value: string;
      detail: string | null;
      tone: ExecutiveTone;
      source: string;
    } => ({
      id,
      label,
      value: UNAVAILABLE,
      detail: null,
      tone: "muted",
      source: "scorecard",
    });

    const cells: ExecutiveCell[] = [
      profileCellToExecutive(
        byId.integrity ?? fallback("integrity", "Integrity"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["critical-gates"] ?? fallback("critical-gates", "Critical Gates"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["evidence-confidence"] ??
          fallback("evidence-confidence", "Evidence Confidence"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["worst-regime"] ?? fallback("worst-regime", "Worst Regime"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["worst-transition"] ??
          fallback("worst-transition", "Worst Transition"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["cost-stress"] ?? fallback("cost-stress", "Cost Stress"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["parameter-area"] ?? fallback("parameter-area", "Parameter Area"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["main-weakness"] ?? fallback("main-weakness", "Main Weakness"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["main-strength"] ?? fallback("main-strength", "Main Strength"),
        studyHref,
      ),
      profileCellToExecutive(
        byId["final-decision"] ??
          fallback("final-decision", "Final Human Decision"),
        studyHref,
      ),
    ];

    return {
      cells,
      evidence,
      strategyId: evidence?.strategyId ?? null,
      strategyVersion: evidence?.strategyVersion ?? null,
      freezeLabel: UNAVAILABLE,
      freezeDetail:
        "P5 Parameter-Freeze / Holdout-Freeze noch nicht als Scorecard-Feld exponiert",
      pin,
    };
  }

  const legacyDetail = pin.cause;
  const useLegacyScorecardCopy = scorecardBind != null;
  return {
    cells: [
      integrityCellForEvidence(overview.recent_experiments, evidence),
      criticalGatesCellForEvidence(gateRuns, focus),
      unavailableScorecardCell(
        "evidence-confidence",
        "Evidence Confidence",
        legacyDetail,
        studyHref,
      ),
      unavailableScorecardCell(
        "worst-regime",
        "Worst Regime",
        legacyDetail,
        studyHref,
      ),
      unavailableScorecardCell(
        "worst-transition",
        "Worst Transition",
        legacyDetail,
        studyHref,
      ),
      useLegacyScorecardCopy
        ? unavailableScorecardCell(
            "cost-stress",
            "Cost Stress",
            legacyDetail,
            studyHref,
          )
        : robustnessInventoryCell(
            "cost-stress",
            "Cost Stress",
            robustnessJobs,
            "cost_stress",
            evidence,
          ),
      useLegacyScorecardCopy
        ? unavailableScorecardCell(
            "parameter-area",
            "Parameter Area",
            legacyDetail,
            studyHref,
          )
        : robustnessInventoryCell(
            "parameter-area",
            "Parameter Area",
            robustnessJobs,
            "parameter_stability",
            evidence,
          ),
      unavailableScorecardCell(
        "main-weakness",
        "Main Weakness",
        legacyDetail,
        studyHref,
      ),
      unavailableScorecardCell(
        "main-strength",
        "Main Strength",
        legacyDetail,
        studyHref,
      ),
      finalDecisionCell(focus),
    ],
    evidence,
    strategyId: evidence?.strategyId ?? null,
    strategyVersion: evidence?.strategyVersion ?? null,
    freezeLabel: UNAVAILABLE,
    freezeDetail:
      "P5 Parameter-Freeze / Holdout-Freeze noch nicht als Scorecard-Feld exponiert",
    pin,
  };
}
