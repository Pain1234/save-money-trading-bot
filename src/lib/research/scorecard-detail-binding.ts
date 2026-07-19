import type { RegimeScorecardRow } from "@/components/research/analytics/RegimeScorecardTable";
import { UNAVAILABLE } from "@/lib/research/labels";
import {
  BACKEND_NOT_AVAILABLE,
  scorecardDisplayValue,
} from "@/lib/research/scorecard-binding";
import type {
  ScorecardDetail,
  ScorecardDetailCostStress,
  ScorecardDetailCostStressOk,
  ScorecardDetailGateFailure,
  ScorecardDetailRegimeRow,
  ScorecardNaMetric,
} from "@/lib/research-api/client";

function metricValue(
  cell: ScorecardNaMetric<unknown> | undefined,
): string | number | null {
  if (!cell || cell.status !== "OK" || cell.value === null || cell.value === undefined) {
    return null;
  }
  return cell.value as string | number;
}

function formatCosts(
  cell: ScorecardDetailRegimeRow["costs"],
): string | null {
  if (!cell || cell.status !== "OK" || !cell.value || typeof cell.value !== "object") {
    return null;
  }
  const v = cell.value;
  const fees = v.fees != null ? String(v.fees) : null;
  const slip = v.slippage_costs != null ? String(v.slippage_costs) : null;
  const fund = v.funding_costs != null ? String(v.funding_costs) : null;
  const parts = [
    fees != null ? `fees=${fees}` : null,
    slip != null ? `slip=${slip}` : null,
    fund != null ? `fund=${fund}` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : null;
}

function behaviourLabel(
  behaviour: ScorecardDetailRegimeRow["behaviour"],
): string | null {
  if (!behaviour || behaviour.status !== "OK") return null;
  const labels = behaviour.labels?.filter(Boolean) ?? [];
  if (labels.length > 0) return labels.join(", ");
  const weakness = behaviour.main_weakness;
  if (weakness && weakness !== BACKEND_NOT_AVAILABLE) return String(weakness);
  const strength = behaviour.main_strength;
  if (strength && strength !== BACKEND_NOT_AVAILABLE) return String(strength);
  return null;
}

/** Map detail regime_rows → RegimeScorecardTable rows (#292 rest / #350). */
export function mapRegimeRowsFromDetail(
  detail: ScorecardDetail | null | undefined,
): RegimeScorecardRow[] {
  if (!detail?.regime_rows?.length) return [];
  return detail.regime_rows.map((row) => ({
    regime: row.cell_id,
    quality: metricValue(row.quality),
    confidence:
      row.confidence?.status === "OK" ? row.confidence.value : null,
    behaviour: behaviourLabel(row.behaviour),
    trades: metricValue(row.trades),
    netPnl: metricValue(row.net_pnl) as string | null,
    maxDd: metricValue(row.max_drawdown) as string | null,
    costs: formatCosts(row.costs),
    benchmarkDelta: metricValue(row.benchmark_delta) as string | null,
  }));
}

export interface CostStressView {
  available: boolean;
  reason: string;
  robustnessRunId: string | null;
  baseNetPnl: string | null;
  elevatedNetPnl: string | null;
  manifestHash: string | null;
}

export function mapCostStressFromDetail(
  costStress: ScorecardDetailCostStress | null | undefined,
): CostStressView {
  if (!costStress) {
    return {
      available: false,
      reason: "Cost-Stress Nicht verfügbar — kein Detail-Payload",
      robustnessRunId: null,
      baseNetPnl: null,
      elevatedNetPnl: null,
      manifestHash: null,
    };
  }
  if (
    costStress.status === "OK" &&
    "boundary" in costStress &&
    costStress.boundary &&
    typeof costStress.boundary === "object"
  ) {
    const boundary = costStress.boundary as {
      base_net_pnl?: string | null;
      combined_elevated_net_pnl?: string | null;
    };
    const ok = costStress as ScorecardDetailCostStressOk;
    return {
      available: true,
      reason: "",
      robustnessRunId: String(ok.robustness_run_id ?? ""),
      baseNetPnl:
        boundary.base_net_pnl != null ? String(boundary.base_net_pnl) : null,
      elevatedNetPnl:
        boundary.combined_elevated_net_pnl != null
          ? String(boundary.combined_elevated_net_pnl)
          : null,
      manifestHash:
        ok.manifest_content_hash != null
          ? String(ok.manifest_content_hash)
          : null,
    };
  }
  const reasonRaw =
    "reason" in costStress && typeof costStress.reason === "string"
      ? costStress.reason
      : "";
  const reason =
    reasonRaw ||
    "Cost-Stress boundary Nicht verfügbar (kein sealed base + combined_elevated)";
  return {
    available: false,
    reason,
    robustnessRunId:
      "robustness_run_id" in costStress &&
      typeof costStress.robustness_run_id === "string"
        ? costStress.robustness_run_id
        : null,
    baseNetPnl: null,
    elevatedNetPnl: null,
    manifestHash: null,
  };
}

export interface TransitionDetailView {
  riskLabel: string | null;
  detail: string | null;
  mae: string | null;
  mfe: string | null;
  transitions: Array<{
    id: string;
    from: string;
    to: string;
  }>;
  transitionsReason: string | null;
}

export function mapTransitionFromDetail(
  detail: ScorecardDetail | null | undefined,
): TransitionDetailView {
  const empty: TransitionDetailView = {
    riskLabel: null,
    detail: null,
    mae: null,
    mfe: null,
    transitions: [],
    transitionsReason: "Classifier-Transitions Nicht verfügbar",
  };
  if (!detail) return empty;

  let riskLabel: string | null = null;
  let mae: string | null = null;
  let mfe: string | null = null;
  let detailLine: string | null = null;

  const tr = detail.transition_risk;
  if (tr && tr.status === "OK" && tr.value && typeof tr.value === "object") {
    const v = tr.value as Record<string, unknown>;
    riskLabel =
      v.risk_label != null && String(v.risk_label) !== BACKEND_NOT_AVAILABLE
        ? String(v.risk_label)
        : null;
    const count = v.transition_count;
    const parts: string[] = [];
    if (count !== undefined && count !== null) {
      parts.push(`transitions=${String(count)}`);
    }
    if (v.mae != null && String(v.mae) !== BACKEND_NOT_AVAILABLE) {
      mae = String(v.mae);
      parts.push(`mae=${mae}`);
    }
    if (v.mfe != null && String(v.mfe) !== BACKEND_NOT_AVAILABLE) {
      mfe = String(v.mfe);
      parts.push(`mfe=${mfe}`);
    }
    detailLine = parts.length > 0 ? parts.join(" · ") : null;
  }

  const ct = detail.classifier_transitions;
  let transitions: TransitionDetailView["transitions"] = [];
  let transitionsReason: string | null = null;
  if (ct && ct.status === "OK" && Array.isArray(ct.transitions)) {
    transitions = ct.transitions.map((t, i) => {
      const from = [t.from_trend, t.from_vol].filter(Boolean).join("/") || "?";
      const to = [t.to_trend, t.to_vol].filter(Boolean).join("/") || "?";
      return {
        id: t.transition_id ?? `tr_${i}`,
        from,
        to,
      };
    });
    if (transitions.length === 0) {
      transitionsReason = "Keine Classifier-Transitions in sealed Labels";
    }
  } else {
    const reason =
      ct && "reason" in ct && typeof ct.reason === "string" && ct.reason
        ? ct.reason
        : "Classifier-Transitions Nicht verfügbar";
    transitionsReason = reason;
  }

  return {
    riskLabel,
    detail: detailLine,
    mae,
    mfe,
    transitions,
    transitionsReason,
  };
}

/** Gate failures that are real FAIL rows (exclude no_bound_gate_run sentinel). */
export function realGateFailures(
  failures: ScorecardDetailGateFailure[] | null | undefined,
): ScorecardDetailGateFailure[] {
  if (!failures?.length) return [];
  return failures.filter(
    (f) =>
      f.status !== BACKEND_NOT_AVAILABLE &&
      f.reason !== "no_bound_gate_run" &&
      (f.name != null || f.outcome != null),
  );
}

export function gateFailuresUnavailableReason(
  failures: ScorecardDetailGateFailure[] | null | undefined,
): string | null {
  if (!failures?.length) {
    return "Gate Failures Nicht verfügbar — kein gebundenes Gate";
  }
  const sentinel = failures.find((f) => f.reason === "no_bound_gate_run");
  if (sentinel && failures.length === 1) {
    return "Kein gebundenes Gate am Scorecard (no_bound_gate_run)";
  }
  if (realGateFailures(failures).length === 0) {
    return "Keine Gate-Failures (alle PASS oder kein gebundenes Gate)";
  }
  return null;
}

export function evidenceInputEntries(
  inputs: Record<string, unknown> | null | undefined,
): Array<{ key: string; value: string }> {
  if (!inputs || typeof inputs !== "object") return [];
  const skip = new Set(["global_profile_summary"]);
  const entries: Array<{ key: string; value: string }> = [];
  for (const [key, raw] of Object.entries(inputs)) {
    if (skip.has(key)) continue;
    if (raw === null || raw === undefined || raw === "") {
      entries.push({ key, value: UNAVAILABLE });
      continue;
    }
    if (typeof raw === "object") {
      try {
        entries.push({ key, value: JSON.stringify(raw) });
      } catch {
        entries.push({ key, value: UNAVAILABLE });
      }
      continue;
    }
    entries.push({ key, value: scorecardDisplayValue(raw as string | number) });
  }
  return entries;
}
