import Link from "next/link";

import {
  ResearchTableFrame,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { Card } from "@/components/ui/Card";
import { displayValue, type ValidationStudyDetail } from "@/lib/research-api/client";

interface ValidationStudyDetailViewProps {
  study: ValidationStudyDetail;
}

const ROBUSTNESS_TYPE_LABELS: Record<string, string> = {
  walk_forward: "Walk-Forward",
  cost_stress: "Kostenstress",
  parameter_stability: "Parameterstabilität",
  bootstrap: "Bootstrap / Monte Carlo",
};

const ROBUSTNESS_TYPE_ORDER = [
  "walk_forward",
  "cost_stress",
  "parameter_stability",
  "bootstrap",
];

const STATUS_LABELS: Record<string, string> = {
  open: "Offen",
  decided: "Entschieden",
};

const OUTCOME_LABELS: Record<string, string> = {
  accept: "Akzeptiert",
  reject: "Abgelehnt",
  inconclusive: "Nicht eindeutig",
};

export function ValidationStudyDetailView({ study }: ValidationStudyDetailViewProps) {
  const robustnessTypes = [
    ...ROBUSTNESS_TYPE_ORDER.filter((t) => study.robustness_by_type[t]),
    ...Object.keys(study.robustness_by_type).filter(
      (t) => !ROBUSTNESS_TYPE_ORDER.includes(t),
    ),
  ];

  return (
    <div className={rs.page} data-testid="validation-detail-ready">
      <Card padding="sm">
        <h2 className={rs.sectionTitle}>Übersicht</h2>
        <dl className="grid gap-3 text-[12px] sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className={rs.label}>Strategie / Version</dt>
            <dd className="mt-0.5 font-mono" data-testid="validation-strategy">
              {displayValue(study.strategy_id)} · {displayValue(study.strategy_version)}
            </dd>
          </div>
          <div>
            <dt className={rs.label}>Studienstatus</dt>
            <dd className="mt-0.5" data-testid="validation-status">
              {STATUS_LABELS[study.status] ?? study.status}
            </dd>
          </div>
          <div>
            <dt className={rs.label}>Fortschritt</dt>
            <dd className="mt-0.5 text-[11px]" data-testid="validation-progress">
              Experimente {study.progress.experiments.complete}/
              {study.progress.experiments.total} · Robustheit{" "}
              {study.progress.robustness.completed}/{study.progress.robustness.total} ·
              Gates {study.progress.gates.pass}/{study.progress.gates.total} bestanden
            </dd>
          </div>
          <div>
            <dt className={rs.label}>Policy-Version</dt>
            <dd className="mt-0.5 font-mono">
              {displayValue(study.reproducibility.policy_version)}
            </dd>
          </div>
        </dl>
        {study.notes && (
          <p className="mt-3 text-[11px] text-text-secondary">{study.notes}</p>
        )}
      </Card>

      <Card padding="sm" data-testid="validation-decision">
        <h2 className={rs.sectionTitle}>Finale Entscheidung</h2>
        {study.decision ? (
          <div className="space-y-1 text-[12px]">
            <p>
              <span className="font-semibold">
                {OUTCOME_LABELS[study.decision.outcome] ?? study.decision.outcome}
              </span>{" "}
              <span className="text-[11px] text-text-muted">
                von {study.decision.decided_by} am{" "}
                {displayValue(study.decision.decided_at)}
              </span>
            </p>
            <p className="text-[11px] text-text-secondary">{study.decision.rationale}</p>
          </div>
        ) : (
          <p className={rs.muted} data-testid="validation-decision-pending">
            Noch keine finale Entscheidung erfasst.
          </p>
        )}
      </Card>

      <Card padding="sm">
        <h2 className={rs.sectionTitle}>Beteiligte Experimente</h2>
        <ResearchTableFrame>
          <table className={rs.table}>
            <thead>
              <tr>
                {["Experiment", "Status", "Net PnL", "Max DD", "Trades"].map((col) => (
                  <th key={col} className={`whitespace-nowrap ${rs.th}`}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {study.experiments.map((exp) => (
                <tr
                  key={exp.experiment_id}
                  className="border-t border-border-subtle"
                  data-testid={`validation-experiment-${exp.experiment_id}`}
                >
                  <td className={`${rs.td} font-mono text-[11px]`}>
                    <Link
                      href={`/dashboard/research/experiments/${encodeURIComponent(exp.experiment_id)}`}
                      className="text-mint hover:underline"
                    >
                      {exp.experiment_id}
                    </Link>
                  </td>
                  <td className={rs.td}>{displayValue(exp.status)}</td>
                  <td className={`${rs.td} font-mono`}>{displayValue(exp.net_pnl)}</td>
                  <td className={`${rs.td} font-mono`}>{displayValue(exp.max_drawdown)}</td>
                  <td className={`${rs.td} font-mono`}>
                    {exp.closed_trades == null ? "Nicht verfügbar" : exp.closed_trades}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResearchTableFrame>
      </Card>

      {robustnessTypes.map((testType) => (
        <Card padding="sm" key={testType} data-testid={`validation-robustness-${testType}`}>
          <h2 className={rs.sectionTitle}>
            {ROBUSTNESS_TYPE_LABELS[testType] ?? testType}
          </h2>
          <ResearchTableFrame>
            <table className={rs.table}>
              <thead>
                <tr>
                  {["Test", "Status", "Kind-Läufe", "Fehler"].map((col) => (
                    <th key={col} className={`whitespace-nowrap ${rs.th}`}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {study.robustness_by_type[testType]?.map((rob) => (
                  <tr key={rob.robustness_id} className="border-t border-border-subtle">
                    <td className={`${rs.td} font-mono text-[11px]`}>
                      <Link
                        href={`/dashboard/research/robustness/${encodeURIComponent(rob.robustness_id)}`}
                        className="text-mint hover:underline"
                      >
                        {rob.robustness_id}
                      </Link>
                    </td>
                    <td className={rs.td}>{displayValue(rob.status)}</td>
                    <td className={`${rs.td} font-mono`}>
                      {rob.manifest
                        ? `${rob.manifest.summary.n_complete}/${rob.manifest.summary.n_children}`
                        : "Nicht verfügbar"}
                    </td>
                    <td className={`${rs.td} font-mono`}>
                      {rob.manifest?.summary.n_failed
                        ? `${rob.manifest.summary.n_failed} fehlgeschlagen`
                        : "Nicht verfügbar"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ResearchTableFrame>
        </Card>
      ))}

      <Card padding="sm" data-testid="validation-gates">
        <h2 className={rs.sectionTitle}>Gate-Ergebnisse</h2>
        {study.gates.length === 0 ? (
          <p className={rs.muted}>Keine Gate-Ergebnisse verknüpft.</p>
        ) : (
          <div className="space-y-3">
            <ResearchTableFrame>
              <table className={rs.table}>
                <thead>
                  <tr>
                    {["Gate-Lauf", "Policy", "Gesamtstatus", "Ausgewertet"].map((col) => (
                      <th key={col} className={`whitespace-nowrap ${rs.th}`}>
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {study.gates.map((gate) => (
                    <tr
                      key={gate.gate_run_id}
                      className="border-t border-border-subtle"
                      data-testid={`validation-gate-${gate.gate_run_id}`}
                    >
                      <td className={`${rs.td} font-mono text-[11px]`}>{gate.gate_run_id}</td>
                      <td className={`${rs.td} font-mono text-[11px]`}>{gate.policy_version}</td>
                      <td className={rs.td}>
                        {gate.overall_status === "pass" ? "Bestanden" : "Nicht bestanden"}
                      </td>
                      <td className={`${rs.td} font-mono text-[11px]`}>
                        {displayValue(gate.evaluated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ResearchTableFrame>
            {study.gates.map((gate) =>
              gate.gates?.length ? (
                <div
                  key={`detail-${gate.gate_run_id}`}
                  data-testid={`validation-gate-detail-${gate.gate_run_id}`}
                >
                  <p className={`${rs.label} mb-1`}>
                    Einzelgates · {gate.gate_run_id}
                  </p>
                  <ResearchTableFrame>
                    <table className={rs.table}>
                      <thead>
                        <tr>
                          {["Name", "Outcome", "Measured", "Threshold", "Reason"].map(
                            (col) => (
                              <th key={col} className={`whitespace-nowrap ${rs.th}`}>
                                {col}
                              </th>
                            ),
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {gate.gates.map((g) => (
                          <tr
                            key={g.name}
                            className="border-t border-border-subtle"
                          >
                            <td className={`${rs.td} font-mono text-[11px]`}>
                              {g.name}
                            </td>
                            <td className={rs.td}>
                              {displayValue(
                                g.outcome ?? (g.passed ? "PASS" : "FAIL"),
                              )}
                            </td>
                            <td className={`${rs.td} font-mono text-[11px]`}>
                              {displayValue(g.measured_value)}
                            </td>
                            <td className={`${rs.td} font-mono text-[11px]`}>
                              {displayValue(g.threshold)}
                            </td>
                            <td className={`${rs.td} text-[11px]`}>
                              {displayValue(g.reason)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </ResearchTableFrame>
                </div>
              ) : null,
            )}
          </div>
        )}
      </Card>

      <Card padding="sm" data-testid="validation-reproducibility">
        <h2 className={rs.sectionTitle}>Reproduzierbarkeit</h2>
        <dl className="grid gap-2 text-[12px] sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className={rs.label}>Git-Commit</dt>
            <dd className="mt-0.5 font-mono text-[11px]">
              {displayValue(study.reproducibility.git_commit)}
            </dd>
          </div>
          <div>
            <dt className={rs.label}>Evaluierungs-Commit</dt>
            <dd className="mt-0.5 font-mono text-[11px]">
              {displayValue(study.reproducibility.evaluation_code_commit)}
            </dd>
          </div>
          <div>
            <dt className={rs.label}>Dataset-ID</dt>
            <dd className="mt-0.5 font-mono text-[11px]">
              {displayValue(study.reproducibility.dataset_id)}
            </dd>
          </div>
          <div>
            <dt className={rs.label}>Dataset-Hash</dt>
            <dd className="mt-0.5 font-mono text-[11px]">
              {displayValue(study.reproducibility.dataset_content_hash)}
            </dd>
          </div>
          <div>
            <dt className={rs.label}>Policy-Hash</dt>
            <dd className="mt-0.5 font-mono text-[11px]">
              {displayValue(study.reproducibility.policy_content_hash)}
            </dd>
          </div>
          <div>
            <dt className={rs.label}>Quelle</dt>
            <dd className="mt-0.5 font-mono text-[11px]">{study.reproducibility.source}</dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
