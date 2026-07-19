import { AnalyticsPanel } from "@/components/research/analytics/AnalyticsPanel";
import {
  evidenceInputEntries,
  gateFailuresUnavailableReason,
  realGateFailures,
  type TransitionDetailView,
} from "@/lib/research/scorecard-detail-binding";
import { scorecardDisplayValue } from "@/lib/research/scorecard-binding";
import { UNAVAILABLE } from "@/lib/research/executive-summary";
import { displayValue, type ScorecardDetail } from "@/lib/research-api/client";
import type { GateRunRecord } from "@/lib/research-api/client";

export interface ForensicsExtras {
  /** Experiment cost metrics when scorecard detail absent. */
  costMetrics?: {
    fees?: string | number | null;
    slippage_costs?: string | number | null;
    funding_costs?: string | number | null;
  } | null;
  /** Walk-forward fold children from robustness manifests. */
  folds?: Array<{
    id: string;
    label: string;
    netPnl: string | null;
    maxDd: string | null;
    trades: number | null;
  }> | null;
  /** Gate runs for history (study.gates or fetchGateRuns). */
  gateHistory?: GateRunRecord[] | null;
}

interface ResearchForensicsSectionProps {
  detail?: ScorecardDetail | null;
  detailError?: string | null;
  transition?: TransitionDetailView | null;
  extras?: ForensicsExtras | null;
  /** Scorecard audit fields when detail missing but summary ready. */
  audit?: {
    scorecardId?: string;
    evaluatedAt?: string | null;
    policyVersion?: string | null;
    policyContentHash?: string | null;
    evidenceContentHash?: string | null;
    runCodeCommit?: string | null;
    evaluationCodeCommit?: string | null;
    status?: string | null;
    invalidationReason?: string | null;
  } | null;
}

/**
 * Research forensics drilldowns (#302) + #292 rest (Evidence / Gate Failures / Refs).
 * Bound to scorecard detail + optional experiment/study extras only.
 */
export function ResearchForensicsSection({
  detail = null,
  detailError = null,
  transition = null,
  extras = null,
  audit = null,
}: ResearchForensicsSectionProps) {
  const inputs = evidenceInputEntries(detail?.evidence_inputs);
  const failures = realGateFailures(detail?.gate_failures);
  const failuresReason = gateFailuresUnavailableReason(detail?.gate_failures);
  const refs = detail?.raw_artifact_refs ?? [];
  const mae = transition?.mae ?? null;
  const mfe = transition?.mfe ?? null;

  return (
    <section className="space-y-2" data-testid="research-forensics-section">
      <div>
        <h2 className="text-[13px] font-semibold text-text-primary">
          Forensics & Evidence
        </h2>
        <p className="mt-0.5 text-[11px] text-text-muted">
          Drilldowns aus Scorecard-Detail (#350) und gebundenen Artefakten —
          fehlende Felder = {UNAVAILABLE}. Keine Promotion.
        </p>
        {detailError ? (
          <p
            className="mt-1 rounded-sm border border-warning/40 bg-warning/10 px-2 py-1.5 text-[12px] text-warning"
            data-testid="forensics-detail-error"
          >
            Scorecard-Detail nicht geladen: {detailError}
          </p>
        ) : null}
      </div>

      <div className="grid gap-2 lg:grid-cols-2">
        <AnalyticsPanel
          id="evidence-inputs"
          title="Evidence Inputs"
          subtitle="Pins aus detail.evidence_inputs"
          unavailable={inputs.length === 0}
          unavailableReason={
            detailError
              ? `Detail-Fehler — Evidence Inputs ${UNAVAILABLE}`
              : "Evidence Inputs Nicht verfügbar — kein Scorecard-Detail"
          }
        >
          <dl
            className="max-h-48 space-y-1 overflow-y-auto text-[11px]"
            data-testid="evidence-inputs-list"
          >
            {inputs.map((row) => (
              <div key={row.key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-2">
                <dt className="truncate text-text-muted">{row.key}</dt>
                <dd className="break-all font-mono">{row.value}</dd>
              </div>
            ))}
          </dl>
        </AnalyticsPanel>

        <AnalyticsPanel
          id="gate-failures"
          title="Gate Failures"
          subtitle="Non-PASS nach sealed gate_evidence_content_hash"
          unavailable={failures.length === 0}
          unavailableReason={failuresReason ?? `Gate Failures ${UNAVAILABLE}`}
        >
          <ul
            className="max-h-48 space-y-1.5 overflow-y-auto text-[12px]"
            data-testid="gate-failures-list"
          >
            {failures.map((f, i) => (
              <li
                key={`${f.name ?? "gate"}-${i}`}
                className="rounded-sm border border-border-subtle px-2 py-1.5"
              >
                <p className="font-mono text-warning">
                  {displayValue(f.name)} · {displayValue(f.outcome ?? (f.passed === false ? "FAIL" : null))}
                </p>
                <p className="mt-0.5 text-[11px] text-text-muted">
                  measured={displayValue(f.measured_value)} · threshold=
                  {displayValue(f.threshold)}
                </p>
                <p className="text-[11px] text-text-secondary">
                  {displayValue(f.reason)}
                </p>
              </li>
            ))}
          </ul>
        </AnalyticsPanel>
      </div>

      <AnalyticsPanel
        id="raw-artifact-refs"
        title="Raw Metric / Artifact Refs"
        subtitle="Layer-Dateien + relative_path + Checksums — Inhalt-Download folgt sicherem Artefakt-GET"
        unavailable={refs.length === 0}
        unavailableReason={
          detailError
            ? `Detail-Fehler — Refs ${UNAVAILABLE}`
            : `Raw Artifact Refs ${UNAVAILABLE}`
        }
      >
        <div className="overflow-x-auto">
          <table
            className="min-w-full text-left text-[11px]"
            data-testid="raw-artifact-refs-table"
          >
            <thead className="text-text-muted">
              <tr>
                <th className="px-2 py-1 font-medium">Name</th>
                <th className="px-2 py-1 font-medium">Path</th>
                <th className="px-2 py-1 font-medium">Checksum</th>
                <th className="px-2 py-1 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {refs.map((ref) => (
                <tr key={ref.name} className="border-t border-border-subtle">
                  <td className="px-2 py-1 font-mono text-mint">{ref.name}</td>
                  <td
                    className="max-w-[16rem] truncate px-2 py-1 font-mono text-[10px]"
                    title={ref.relative_path ?? undefined}
                    data-testid={`raw-artifact-path-${ref.name}`}
                  >
                    {displayValue(ref.relative_path)}
                  </td>
                  <td className="max-w-[14rem] truncate px-2 py-1 font-mono">
                    {displayValue(ref.checksum_sha256)}
                  </td>
                  <td className="px-2 py-1 font-mono">
                    {scorecardDisplayValue(ref.status)}
                    {ref.present === false ? " · absent" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-text-muted" data-testid="raw-artifact-download-note">
          relative_path ist Inventar aus Scorecard-Detail. Inhalt / Download bleibt{" "}
          {UNAVAILABLE} bis ein sicherer read-only Artefakt-Endpunkt existiert
          (Folge-Issue #357 — kein Fake-Link).
        </p>
      </AnalyticsPanel>

      <div className="grid gap-2 lg:grid-cols-2 xl:grid-cols-3">
        <AnalyticsPanel
          id="mfe-mae"
          title="MFE / MAE"
          subtitle="Nur aus sealed transition_risk — nie erfunden"
          unavailable={
            (mae == null || mae === "") && (mfe == null || mfe === "")
          }
          unavailableReason={`MFE/MAE ${UNAVAILABLE} (transition_risk.mae/mfe fehlen oder NOT_AVAILABLE)`}
        >
          <dl className="space-y-1 text-[12px]" data-testid="mfe-mae-bound">
            <div>
              <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
                MAE
              </dt>
              <dd className="font-mono">{scorecardDisplayValue(mae)}</dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
                MFE
              </dt>
              <dd className="font-mono">{scorecardDisplayValue(mfe)}</dd>
            </div>
          </dl>
        </AnalyticsPanel>

        <AnalyticsPanel
          id="forensics-costs"
          title="Costs"
          subtitle="Experiment-Kennzahlen oder Regime-Kosten"
          unavailable={
            !extras?.costMetrics ||
            (extras.costMetrics.fees == null &&
              extras.costMetrics.slippage_costs == null &&
              extras.costMetrics.funding_costs == null)
          }
          unavailableReason={`Kosten-Kennzahlen ${UNAVAILABLE}`}
        >
          <dl className="space-y-1 text-[12px]" data-testid="forensics-costs-bound">
            <div>
              <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
                Fees
              </dt>
              <dd className="font-mono">
                {displayValue(extras?.costMetrics?.fees)}
              </dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
                Slippage
              </dt>
              <dd className="font-mono">
                {displayValue(extras?.costMetrics?.slippage_costs)}
              </dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
                Funding
              </dt>
              <dd className="font-mono">
                {displayValue(extras?.costMetrics?.funding_costs)}
              </dd>
            </div>
          </dl>
        </AnalyticsPanel>

        <AnalyticsPanel
          id="freeze-spec"
          title="Freeze Specification"
          subtitle="Spec-Freeze / P5 — noch nicht exponiert"
          unavailable
          unavailableReason={`Freeze Specification ${UNAVAILABLE} (kein API-Feld bis Spec-Freeze)`}
        />
      </div>

      <div className="grid gap-2 lg:grid-cols-2">
        <AnalyticsPanel
          id="folds"
          title="Folds"
          subtitle="Walk-Forward children aus Robustness-Manifest"
          unavailable={!extras?.folds || extras.folds.length === 0}
          unavailableReason={`Folds ${UNAVAILABLE} — kein Walk-Forward-Manifest gebunden`}
        >
          <div className="overflow-x-auto">
            <table
              className="min-w-full text-left text-[11px]"
              data-testid="forensics-folds-table"
            >
              <thead className="text-text-muted">
                <tr>
                  <th className="px-2 py-1 font-medium">Fold</th>
                  <th className="px-2 py-1 font-medium">Net PnL</th>
                  <th className="px-2 py-1 font-medium">Max DD</th>
                  <th className="px-2 py-1 font-medium">Trades</th>
                </tr>
              </thead>
              <tbody>
                {extras?.folds?.map((fold) => (
                  <tr key={fold.id} className="border-t border-border-subtle">
                    <td className="px-2 py-1 font-mono text-mint">
                      {fold.label || fold.id}
                    </td>
                    <td className="px-2 py-1 font-mono">
                      {displayValue(fold.netPnl)}
                    </td>
                    <td className="px-2 py-1 font-mono">
                      {displayValue(fold.maxDd)}
                    </td>
                    <td className="px-2 py-1 font-mono">
                      {displayValue(fold.trades)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AnalyticsPanel>

        <AnalyticsPanel
          id="gate-history"
          title="Gate History"
          subtitle="Gebundene Gate-Läufe (Study / run)"
          unavailable={!extras?.gateHistory || extras.gateHistory.length === 0}
          unavailableReason={`Gate History ${UNAVAILABLE}`}
        >
          <ul
            className="max-h-48 space-y-2 overflow-y-auto text-[12px]"
            data-testid="gate-history-list"
          >
            {extras?.gateHistory?.map((gate) => (
              <li
                key={gate.gate_run_id}
                className="rounded-sm border border-border-subtle px-2 py-1.5"
              >
                <p className="font-mono text-[11px] text-mint">
                  {gate.gate_run_id}
                </p>
                <p className="mt-0.5 text-[11px] text-text-muted">
                  {gate.overall_status} · policy={gate.policy_version} ·{" "}
                  {displayValue(gate.evaluated_at)}
                </p>
                {gate.gates?.length ? (
                  <ul className="mt-1 space-y-0.5 border-t border-border-subtle pt-1 font-mono text-[10px]">
                    {gate.gates.map((g) => (
                      <li key={g.name}>
                        {g.name}:{" "}
                        {g.outcome ?? (g.passed ? "PASS" : "FAIL")} · measured=
                        {displayValue(g.measured_value)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </AnalyticsPanel>
      </div>

      <div className="grid gap-2 lg:grid-cols-2">
        <AnalyticsPanel
          id="data-lineage"
          title="Data Lineage"
          subtitle="Dataset / commits / evidence hashes"
          unavailable={!detail?.evidence_inputs && !audit}
          unavailableReason={`Data Lineage ${UNAVAILABLE}`}
        >
          <dl
            className="grid gap-1.5 text-[11px] sm:grid-cols-2"
            data-testid="data-lineage-list"
          >
            {(
              [
                ["dataset_id", detail?.evidence_inputs?.dataset_id],
                [
                  "dataset_content_hash",
                  detail?.evidence_inputs?.dataset_content_hash,
                ],
                [
                  "run_code_commit",
                  detail?.evidence_inputs?.run_code_commit ??
                    audit?.runCodeCommit,
                ],
                [
                  "evaluation_code_commit",
                  detail?.evidence_inputs?.evaluation_code_commit ??
                    audit?.evaluationCodeCommit,
                ],
                [
                  "evidence_content_hash",
                  detail?.evidence_inputs?.evidence_content_hash ??
                    audit?.evidenceContentHash,
                ],
                [
                  "gate_evidence_content_hash",
                  detail?.evidence_inputs?.gate_evidence_content_hash,
                ],
              ] as Array<[string, unknown]>
            ).map(([label, value]) => (
              <div key={label}>
                <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
                  {label}
                </dt>
                <dd className="break-all font-mono">
                  {displayValue(
                    value === null || value === undefined || value === ""
                      ? null
                      : String(value),
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </AnalyticsPanel>

        <AnalyticsPanel
          id="audit-metadata"
          title="Audit Metadata"
          subtitle="Scorecard / Policy — append-only Status"
          unavailable={!audit && !detail}
          unavailableReason={`Audit Metadata ${UNAVAILABLE}`}
        >
          <dl
            className="grid gap-1.5 text-[11px] sm:grid-cols-2"
            data-testid="audit-metadata-list"
          >
            {(
              [
                [
                  "scorecard_id",
                  detail?.scorecard_id ?? audit?.scorecardId,
                ],
                [
                  "evaluated_at",
                  detail?.evidence_inputs?.evaluated_at ?? audit?.evaluatedAt,
                ],
                [
                  "policy_version",
                  detail?.evidence_inputs?.policy_version ??
                    audit?.policyVersion,
                ],
                [
                  "policy_content_hash",
                  detail?.evidence_inputs?.policy_content_hash ??
                    audit?.policyContentHash,
                ],
                ["status", detail?.status ?? audit?.status],
                [
                  "invalidation_reason",
                  detail?.evidence_inputs?.invalidation_reason ??
                    audit?.invalidationReason,
                ],
                ["promotion_action", detail?.promotion_action ?? "none"],
                [
                  "decision_binding",
                  detail != null ? String(detail.decision_binding) : null,
                ],
              ] as Array<[string, unknown]>
            ).map(([label, value]) => (
              <div key={label}>
                <dt className="text-[10px] uppercase tracking-[0.06em] text-text-muted">
                  {label}
                </dt>
                <dd className="break-all font-mono">
                  {displayValue(
                    value === null || value === undefined || value === ""
                      ? null
                      : String(value),
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </AnalyticsPanel>
      </div>
    </section>
  );
}
