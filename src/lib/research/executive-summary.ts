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

export interface ExecutiveSummary {
  cells: ExecutiveCell[];
  strategyId: string | null;
  strategyVersion: string | null;
  freezeLabel: string;
  freezeDetail: string;
}

function jobCounts(jobs: RobustnessJobSummary[], testType: string) {
  const matched = jobs.filter((j) => j.test_type === testType);
  const complete = matched.filter(
    (j) => j.status === "completed" || j.status === "complete",
  ).length;
  const failed = matched.filter((j) => j.status === "failed").length;
  const running = matched.filter(
    (j) => j.status === "running" || j.status === "queued",
  ).length;
  return { total: matched.length, complete, failed, running };
}

function integrityCell(
  experiments: ResearchExperimentSummary[],
): ExecutiveCell {
  if (experiments.length === 0) {
    return {
      id: "integrity",
      label: "Integrity",
      value: UNAVAILABLE,
      detail: "Keine Experimente zur Prüfung",
      tone: "muted",
      href: null,
      source: "experiment.integrity_ok",
    };
  }

  const broken = experiments.filter((e) => e.integrity_ok === false);
  if (broken.length > 0) {
    return {
      id: "integrity",
      label: "Integrity",
      value: "INVALID",
      detail: `${broken.length} mit Integrity-Fehler (Registry)`,
      tone: "danger",
      href: `/dashboard/research/experiments/${encodeURIComponent(broken[0]!.experiment_id)}`,
      source: "experiment.integrity_ok",
    };
  }

  return {
    id: "integrity",
    label: "Integrity",
    value: "VALID",
    detail: `${experiments.length} recent — Registry-Checksummen ok`,
    tone: "mint",
    href: null,
    source: "experiment.integrity_ok",
  };
}

function criticalGatesCell(gateRuns: GateRunRecord[]): ExecutiveCell {
  const active = gateRuns.filter((g) => g.status === "active");
  if (active.length === 0) {
    return {
      id: "critical-gates",
      label: "Critical Gates",
      value: UNAVAILABLE,
      detail: "Keine aktiven Gate-Runs (#248)",
      tone: "muted",
      href: "/dashboard/research/validation",
      source: "gates.overall_status",
    };
  }

  const pass = active.filter((g) => g.overall_status === "pass").length;
  const fail = active.filter((g) => g.overall_status === "fail").length;
  const latest = [...active].sort((a, b) =>
    b.evaluated_at.localeCompare(a.evaluated_at),
  )[0]!;

  if (fail > 0) {
    return {
      id: "critical-gates",
      label: "Critical Gates",
      value: "FAIL",
      detail: `${fail} fail / ${pass} pass (active)`,
      tone: "danger",
      href: "/dashboard/research/validation",
      source: "gates.overall_status",
    };
  }

  return {
    id: "critical-gates",
    label: "Critical Gates",
    value: "PASS",
    detail: `${pass} active pass · latest ${latest.policy_version}`,
    tone: "mint",
    href: "/dashboard/research/validation",
    source: "gates.overall_status",
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
): ExecutiveCell {
  const counts = jobCounts(jobs, testType);
  if (counts.total === 0) {
    return unavailableScorecardCell(
      id,
      label,
      `Scorecard-Feld fehlt · keine ${testType}-Jobs`,
      "/dashboard/research/robustness",
    );
  }

  return {
    id,
    label,
    value: UNAVAILABLE,
    detail: `Scorecard fehlt · Jobs ${counts.complete} complete / ${counts.failed} failed / ${counts.running} running`,
    tone: "muted",
    href: "/dashboard/research/robustness",
    source: `robustness.test_type=${testType}`,
  };
}

function finalDecisionCell(studies: ValidationStudyDetail[]): ExecutiveCell {
  if (studies.length === 0) {
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

  const decided = [...studies]
    .filter((s) => s.status === "decided" && s.decision != null)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  if (decided.length > 0) {
    const study = decided[0]!;
    const outcome = study.decision!.outcome;
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
      detail: study.name,
      tone,
      href: `/dashboard/research/validation/${encodeURIComponent(study.study_id)}`,
      source: "validation.decision.outcome",
    };
  }

  const open = studies.filter((s) => s.status === "open");
  const latestOpen = [...open].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  )[0];

  return {
    id: "final-decision",
    label: "Final Decision",
    value: "pending",
    detail: latestOpen
      ? `${open.length} open · ${latestOpen.name}`
      : `${studies.length} Studien ohne Decision`,
    tone: "warning",
    href: latestOpen
      ? `/dashboard/research/validation/${encodeURIComponent(latestOpen.study_id)}`
      : "/dashboard/research/validation",
    source: "validation.status",
  };
}

/**
 * Gate-first executive summary (#299).
 * Binds only existing Research / Gates / Validation / Robustness APIs.
 * Scorecard fields without runtime (#291/#295) stay "Nicht verfügbar".
 */
export function buildExecutiveSummary(input: {
  overview: ResearchOverview;
  gateRuns: GateRunRecord[];
  studies: ValidationStudyDetail[];
  robustnessJobs: RobustnessJobSummary[];
}): ExecutiveSummary {
  const { overview, gateRuns, studies, robustnessJobs } = input;

  const latestStudy = [...studies].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  )[0];

  const strategyId =
    latestStudy?.strategy_id ??
    overview.known_strategy_ids[0] ??
    overview.recent_experiments.find((e) => e.strategy_id)?.strategy_id ??
    null;

  const strategyVersion =
    latestStudy?.strategy_version ??
    overview.recent_experiments[0]?.strategy_version ??
    null;

  return {
    cells: [
      integrityCell(overview.recent_experiments),
      criticalGatesCell(gateRuns),
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
      ),
      robustnessInventoryCell(
        "parameter-area",
        "Parameter Area",
        robustnessJobs,
        "parameter_stability",
      ),
      finalDecisionCell(studies),
    ],
    strategyId,
    strategyVersion,
    freezeLabel: UNAVAILABLE,
    freezeDetail:
      "P5 Parameter-Freeze / Holdout-Freeze noch nicht als Scorecard-Feld exponiert",
  };
}
