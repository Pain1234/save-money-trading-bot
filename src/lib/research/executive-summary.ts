import type {
  GateRunRecord,
  ResearchExperimentSummary,
  ResearchOverview,
  RobustnessJobSummary,
  ValidationStudyDetail,
} from "@/lib/research-api/client";

export const UNAVAILABLE = "Nicht verfügbar";

export type ExecutiveTone = "mint" | "danger" | "warning" | "muted";

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
}

export interface ExecutiveSummary {
  cells: ExecutiveCell[];
  /** Single Validation Study that all bound cells refer to — or null. */
  evidence: ExecutiveEvidenceAnchor | null;
  strategyId: string | null;
  strategyVersion: string | null;
  freezeLabel: string;
  freezeDetail: string;
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
  return {
    studyId: study.study_id,
    studyName: study.name,
    experimentId: study.experiment_id,
    runId: study.run_id,
    strategyId: study.strategy_id,
    strategyVersion: study.strategy_version,
    gateRunIds: [...study.gate_run_ids],
    robustnessIds: [...study.robustness_ids],
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

/** Robustness jobs pinned to the evidence study only. */
export function filterJobsForEvidence(
  jobs: RobustnessJobSummary[],
  evidence: ExecutiveEvidenceAnchor,
  testType: string,
): RobustnessJobSummary[] {
  const pinned = new Set(evidence.robustnessIds);
  return jobs.filter((j) => {
    if (j.test_type !== testType) return false;
    if (pinned.has(j.robustness_id)) return true;
    return j.base_experiment_id === evidence.experimentId;
  });
}

/** Active gate runs that belong to the evidence study. */
export function filterGatesForEvidence(
  gateRuns: GateRunRecord[],
  evidence: ExecutiveEvidenceAnchor,
): GateRunRecord[] {
  const pinnedIds = new Set(evidence.gateRunIds);
  return gateRuns.filter((g) => {
    if (g.status !== "active") return false;
    if (pinnedIds.has(g.gate_run_id)) return true;
    if (evidence.runId && g.run_id === evidence.runId) return true;
    return g.experiment_id === evidence.experimentId;
  });
}

function findPinnedExperiment(
  experiments: ResearchExperimentSummary[],
  evidence: ExecutiveEvidenceAnchor,
): ResearchExperimentSummary | null {
  if (evidence.runId) {
    const byRun = experiments.find((e) => e.run_id === evidence.runId);
    if (byRun) return byRun;
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
  evidence: ExecutiveEvidenceAnchor | null,
): ExecutiveCell {
  if (!evidence) {
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

  const bound = filterGatesForEvidence(gateRuns, evidence);
  if (bound.length === 0) {
    return {
      id: "critical-gates",
      label: "Critical Gates",
      value: UNAVAILABLE,
      detail: `Study ${evidence.studyId}: keine gebundenen aktiven Gate-Runs`,
      tone: "muted",
      href: `/dashboard/research/validation/${encodeURIComponent(evidence.studyId)}`,
      source: "gates (study-bound)",
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
      source: "gates.overall_status (study-bound)",
    };
  }

  return {
    id: "critical-gates",
    label: "Critical Gates",
    value: "PASS",
    detail: `${pass} pass · policy ${latest.policy_version} · Study ${evidence.studyId}`,
    tone: "mint",
    href: `/dashboard/research/validation/${encodeURIComponent(evidence.studyId)}`,
    source: "gates.overall_status (study-bound)",
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
      label: "Final Decision",
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
      label: "Final Decision",
      value: outcome.toUpperCase(),
      detail: `${study.name} · ${study.study_id}`,
      tone,
      href,
      source: "validation.decision.outcome (anchor)",
    };
  }

  return {
    id: "final-decision",
    label: "Final Decision",
    value: "pending",
    detail: `${study.name} · ${study.study_id}`,
    tone: "warning",
    href,
    source: "validation.status (anchor)",
  };
}

/**
 * Gate-first executive summary (#299).
 * All Decision / Gates / Strategy / Integrity / robustness inventory cells
 * share one Validation Study evidence identity when present.
 */
export function buildExecutiveSummary(input: {
  overview: ResearchOverview;
  gateRuns: GateRunRecord[];
  studies: ValidationStudyDetail[];
  robustnessJobs: RobustnessJobSummary[];
}): ExecutiveSummary {
  const { overview, gateRuns, studies, robustnessJobs } = input;
  const focus = selectEvidenceStudy(studies);
  const evidence = focus ? toEvidenceAnchor(focus) : null;

  return {
    cells: [
      integrityCellForEvidence(overview.recent_experiments, evidence),
      criticalGatesCellForEvidence(gateRuns, evidence),
      unavailableScorecardCell(
        "evidence-confidence",
        "Evidence Confidence",
        "Scorecard Layer 3 noch nicht angebunden",
      ),
      unavailableScorecardCell(
        "worst-regime",
        "Worst Regime",
        "Regime-Scorecard noch nicht angebunden",
      ),
      robustnessInventoryCell(
        "cost-stress",
        "Cost Stress",
        robustnessJobs,
        "cost_stress",
        evidence,
      ),
      robustnessInventoryCell(
        "parameter-area",
        "Parameter Area",
        robustnessJobs,
        "parameter_stability",
        evidence,
      ),
      finalDecisionCell(focus),
    ],
    evidence,
    strategyId: evidence?.strategyId ?? null,
    strategyVersion: evidence?.strategyVersion ?? null,
    freezeLabel: UNAVAILABLE,
    freezeDetail:
      "P5 Parameter-Freeze / Holdout-Freeze noch nicht als Scorecard-Feld exponiert",
  };
}
