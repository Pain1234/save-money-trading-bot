import Link from "next/link";

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
    <div className="space-y-4" data-testid="validation-detail-ready">
      <Card padding="sm">
        <h2 className="mb-3 text-sm font-medium">Übersicht</h2>
        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Strategie / Version
            </dt>
            <dd className="mt-0.5 font-mono" data-testid="validation-strategy">
              {displayValue(study.strategy_id)} · {displayValue(study.strategy_version)}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Studienstatus
            </dt>
            <dd className="mt-0.5" data-testid="validation-status">
              {STATUS_LABELS[study.status] ?? study.status}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Fortschritt
            </dt>
            <dd className="mt-0.5 text-xs" data-testid="validation-progress">
              Experimente {study.progress.experiments.complete}/
              {study.progress.experiments.total} · Robustheit{" "}
              {study.progress.robustness.completed}/{study.progress.robustness.total} ·
              Gates {study.progress.gates.pass}/{study.progress.gates.total} bestanden
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Policy-Version
            </dt>
            <dd className="mt-0.5 font-mono">
              {displayValue(study.reproducibility.policy_version)}
            </dd>
          </div>
        </dl>
        {study.notes && (
          <p className="mt-3 text-xs text-text-secondary">{study.notes}</p>
        )}
      </Card>

      <Card padding="sm" data-testid="validation-decision">
        <h2 className="mb-3 text-sm font-medium">Finale Entscheidung</h2>
        {study.decision ? (
          <div className="space-y-1 text-sm">
            <p>
              <span className="font-medium">
                {OUTCOME_LABELS[study.decision.outcome] ?? study.decision.outcome}
              </span>{" "}
              <span className="text-xs text-text-muted">
                von {study.decision.decided_by} am{" "}
                {displayValue(study.decision.decided_at)}
              </span>
            </p>
            <p className="text-xs text-text-secondary">{study.decision.rationale}</p>
          </div>
        ) : (
          <p className="text-sm text-text-muted" data-testid="validation-decision-pending">
            Noch keine finale Entscheidung erfasst.
          </p>
        )}
      </Card>

      <Card padding="sm">
        <h2 className="mb-3 text-sm font-medium">Beteiligte Experimente</h2>
        <div className="overflow-x-auto rounded-xl border border-border-subtle">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-bg-elevated text-text-muted">
              <tr>
                {["Experiment", "Status", "Net PnL", "Max DD", "Trades"].map((col) => (
                  <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
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
                  <td className="px-3 py-2 font-mono text-xs">
                    <Link
                      href={`/dashboard/research/experiments/${encodeURIComponent(exp.experiment_id)}`}
                      className="text-mint hover:underline"
                    >
                      {exp.experiment_id}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{displayValue(exp.status)}</td>
                  <td className="px-3 py-2 font-mono">{displayValue(exp.net_pnl)}</td>
                  <td className="px-3 py-2 font-mono">{displayValue(exp.max_drawdown)}</td>
                  <td className="px-3 py-2 font-mono">
                    {exp.closed_trades == null ? "Nicht verfügbar" : exp.closed_trades}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {robustnessTypes.map((testType) => (
        <Card padding="sm" key={testType} data-testid={`validation-robustness-${testType}`}>
          <h2 className="mb-3 text-sm font-medium">
            {ROBUSTNESS_TYPE_LABELS[testType] ?? testType}
          </h2>
          <div className="overflow-x-auto rounded-xl border border-border-subtle">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-bg-elevated text-text-muted">
                <tr>
                  {["Test", "Status", "Kind-Läufe", "Fehler"].map((col) => (
                    <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {study.robustness_by_type[testType]?.map((rob) => (
                  <tr key={rob.robustness_id} className="border-t border-border-subtle">
                    <td className="px-3 py-2 font-mono text-xs">
                      <Link
                        href={`/dashboard/research/robustness/${encodeURIComponent(rob.robustness_id)}`}
                        className="text-mint hover:underline"
                      >
                        {rob.robustness_id}
                      </Link>
                    </td>
                    <td className="px-3 py-2">{displayValue(rob.status)}</td>
                    <td className="px-3 py-2 font-mono">
                      {rob.manifest
                        ? `${rob.manifest.summary.n_complete}/${rob.manifest.summary.n_children}`
                        : "Nicht verfügbar"}
                    </td>
                    <td className="px-3 py-2 font-mono">
                      {rob.manifest?.summary.n_failed
                        ? `${rob.manifest.summary.n_failed} fehlgeschlagen`
                        : "Nicht verfügbar"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}

      <Card padding="sm" data-testid="validation-gates">
        <h2 className="mb-3 text-sm font-medium">Gate-Ergebnisse</h2>
        {study.gates.length === 0 ? (
          <p className="text-sm text-text-muted">Keine Gate-Ergebnisse verknüpft.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border-subtle">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-bg-elevated text-text-muted">
                <tr>
                  {["Gate-Lauf", "Policy", "Gesamtstatus", "Ausgewertet"].map((col) => (
                    <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
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
                    <td className="px-3 py-2 font-mono text-xs">{gate.gate_run_id}</td>
                    <td className="px-3 py-2 font-mono text-xs">{gate.policy_version}</td>
                    <td className="px-3 py-2">
                      {gate.overall_status === "pass" ? "Bestanden" : "Nicht bestanden"}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {displayValue(gate.evaluated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card padding="sm" data-testid="validation-reproducibility">
        <h2 className="mb-3 text-sm font-medium">Reproduzierbarkeit</h2>
        <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Git-Commit
            </dt>
            <dd className="mt-0.5 font-mono text-xs">
              {displayValue(study.reproducibility.git_commit)}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Evaluierungs-Commit
            </dt>
            <dd className="mt-0.5 font-mono text-xs">
              {displayValue(study.reproducibility.evaluation_code_commit)}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Dataset-ID
            </dt>
            <dd className="mt-0.5 font-mono text-xs">
              {displayValue(study.reproducibility.dataset_id)}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Dataset-Hash
            </dt>
            <dd className="mt-0.5 font-mono text-xs">
              {displayValue(study.reproducibility.dataset_content_hash)}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Policy-Hash
            </dt>
            <dd className="mt-0.5 font-mono text-xs">
              {displayValue(study.reproducibility.policy_content_hash)}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">Quelle</dt>
            <dd className="mt-0.5 font-mono text-xs">{study.reproducibility.source}</dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
