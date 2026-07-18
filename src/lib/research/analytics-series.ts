import type { ExecutiveEvidenceAnchor } from "@/lib/research/executive-summary";
import type {
  ResearchExperimentDetail,
  ResearchSeriesPoint,
} from "@/lib/research-api/client";

/**
 * Serien nur übernehmen, wenn der Detail-Response exakt den Evidence-Pin trifft.
 * `GET /experiments/{id}` liefert den neuesten Registry-Eintrag — ohne Run-Check
 * würden neuere Runs in eine Study mit älterem Pin leaken (#300).
 */
export function pinnedRunMatchesDetail(
  evidence: ExecutiveEvidenceAnchor,
  detail: Pick<ResearchExperimentDetail, "summary">,
): boolean {
  if (detail.summary.experiment_id !== evidence.experimentId) {
    return false;
  }
  if (!evidence.runId) {
    // Kein Run-Pin → keine Serien (nicht still den neuesten Registry-Run nehmen).
    return false;
  }
  return detail.summary.run_id === evidence.runId;
}

/** Equity-Punkte ohne Wert weglassen — nie still mit 0 füllen. */
export type EquitySeriesPoint = Omit<ResearchSeriesPoint, "equity"> & {
  equity: number;
};

export function sanitizeEquitySeries(
  points: ResearchSeriesPoint[] | null | undefined,
): EquitySeriesPoint[] {
  if (!points?.length) return [];
  return points.filter(
    (p): p is EquitySeriesPoint =>
      typeof p.equity === "number" && Number.isFinite(p.equity),
  );
}

/**
 * Drawdown-Punkte ohne Wert weglassen — `(drawdown ?? 0)` würde Nullwerte erfinden.
 * Leere Liste nach Filter → Aufrufer zeigt „Nicht verfügbar“.
 */
export type DrawdownSeriesPoint = Omit<ResearchSeriesPoint, "drawdown"> & {
  drawdown: number;
};

export function sanitizeDrawdownSeries(
  points: ResearchSeriesPoint[] | null | undefined,
): DrawdownSeriesPoint[] {
  if (!points?.length) return [];
  return points.filter(
    (p): p is DrawdownSeriesPoint =>
      typeof p.drawdown === "number" && Number.isFinite(p.drawdown),
  );
}
