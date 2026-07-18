import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { displayValue, type RobustnessManifest } from "@/lib/research-api/client";

interface RobustnessManifestViewProps {
  manifest: RobustnessManifest | null;
}

export function RobustnessManifestView({ manifest }: RobustnessManifestViewProps) {
  if (!manifest) {
    return (
      <Card padding="sm" data-testid="robustness-manifest-pending">
        <p className="text-sm text-text-muted">
          Noch kein Artefakt — Ergebnisse erscheinen nach Abschluss des Tests.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-4" data-testid="robustness-manifest-ready">
      <Card padding="sm">
        <h2 className="mb-3 text-sm font-medium">Zusammenfassung</h2>
        <dl className="grid gap-2 sm:grid-cols-3 text-sm">
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Kind-Läufe
            </dt>
            <dd className="mt-0.5 font-mono">{manifest.summary.n_children}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Abgeschlossen
            </dt>
            <dd className="mt-0.5 font-mono">{manifest.summary.n_complete}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-text-muted">
              Fehlgeschlagen
            </dt>
            <dd
              className={`mt-0.5 font-mono ${manifest.summary.n_failed > 0 ? "text-amber-300" : ""}`}
            >
              {manifest.summary.n_failed}
            </dd>
          </div>
        </dl>
      </Card>

      {manifest.bootstrap_result && (
        <Card padding="sm" data-testid="robustness-bootstrap-result">
          <h2 className="mb-3 text-sm font-medium">Bootstrap-Ergebnis</h2>
          <p className="mb-2 text-xs text-text-muted">
            Block-Länge {manifest.bootstrap_result.block_length}, Simulationen{" "}
            {manifest.bootstrap_result.n_simulations}, Seed {manifest.bootstrap_result.seed}
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-text-muted">
                Netto-PnL Quantile
              </p>
              <pre className="overflow-x-auto rounded border border-border-subtle bg-bg-elevated p-2 text-xs">
                {JSON.stringify(manifest.bootstrap_result.net_pnl_quantiles, null, 2)}
              </pre>
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-text-muted">
                Max-Drawdown Quantile
              </p>
              <pre className="overflow-x-auto rounded border border-border-subtle bg-bg-elevated p-2 text-xs">
                {JSON.stringify(manifest.bootstrap_result.max_drawdown_quantiles, null, 2)}
              </pre>
            </div>
          </div>
        </Card>
      )}

      <Card padding="sm">
        <h2 className="mb-3 text-sm font-medium">Kind-Läufe</h2>
        <div className="overflow-x-auto rounded-xl border border-border-subtle">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-bg-elevated text-text-muted">
              <tr>
                {[
                  "ID",
                  "Experiment",
                  "Status",
                  "Net PnL",
                  "Max DD",
                  "Trades",
                  "Fehler",
                ].map((col) => (
                  <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {manifest.children.map((child) => (
                <tr
                  key={child.child_id}
                  className="border-t border-border-subtle"
                  data-testid={`robustness-child-${child.child_id}`}
                >
                  <td className="px-3 py-2 font-mono text-xs">{child.child_id}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {child.experiment_id ? (
                      <Link
                        href={`/dashboard/research/experiments/${encodeURIComponent(child.experiment_id)}`}
                        className="text-mint hover:underline"
                      >
                        {child.experiment_id}
                      </Link>
                    ) : (
                      "Nicht verfügbar"
                    )}
                  </td>
                  <td className="px-3 py-2">{displayValue(child.status)}</td>
                  <td className="px-3 py-2 font-mono">{displayValue(child.net_pnl)}</td>
                  <td className="px-3 py-2 font-mono">
                    {displayValue(child.max_drawdown)}
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {child.closed_trades == null ? "Nicht verfügbar" : child.closed_trades}
                  </td>
                  <td className="px-3 py-2 text-xs text-red-300">
                    {displayValue(child.error)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
