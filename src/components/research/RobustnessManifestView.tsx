import Link from "next/link";

import {
  ResearchTableFrame,
  rs,
} from "@/components/research/chrome/ResearchPageChrome";
import { Card } from "@/components/ui/Card";
import { displayValue, type RobustnessManifest } from "@/lib/research-api/client";

interface RobustnessManifestViewProps {
  manifest: RobustnessManifest | null;
}

export function RobustnessManifestView({ manifest }: RobustnessManifestViewProps) {
  if (!manifest) {
    return (
      <Card padding="sm" data-testid="robustness-manifest-pending">
        <p className={rs.muted}>
          Noch kein Artefakt — Ergebnisse erscheinen nach Abschluss des Tests.
        </p>
      </Card>
    );
  }

  return (
    <div className={rs.page} data-testid="robustness-manifest-ready">
      <Card padding="sm">
        <h2 className={rs.sectionTitle}>Zusammenfassung</h2>
        <dl className="grid gap-2 sm:grid-cols-3 text-[12px]">
          <div>
            <dt className={rs.label}>Kind-Läufe</dt>
            <dd className="mt-0.5 font-mono">{manifest.summary.n_children}</dd>
          </div>
          <div>
            <dt className={rs.label}>Abgeschlossen</dt>
            <dd className="mt-0.5 font-mono">{manifest.summary.n_complete}</dd>
          </div>
          <div>
            <dt className={rs.label}>Fehlgeschlagen</dt>
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
          <h2 className={rs.sectionTitle}>Bootstrap-Ergebnis</h2>
          <p className={`mb-2 ${rs.muted}`}>
            Block-Länge {manifest.bootstrap_result.block_length}, Simulationen{" "}
            {manifest.bootstrap_result.n_simulations}, Seed {manifest.bootstrap_result.seed}
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className={`mb-1 ${rs.label}`}>Netto-PnL Quantile</p>
              <pre className="overflow-x-auto rounded-sm border border-border-subtle bg-bg-elevated p-2 text-[12px]">
                {JSON.stringify(manifest.bootstrap_result.net_pnl_quantiles, null, 2)}
              </pre>
            </div>
            <div>
              <p className={`mb-1 ${rs.label}`}>Max-Drawdown Quantile</p>
              <pre className="overflow-x-auto rounded-sm border border-border-subtle bg-bg-elevated p-2 text-[12px]">
                {JSON.stringify(manifest.bootstrap_result.max_drawdown_quantiles, null, 2)}
              </pre>
            </div>
          </div>
        </Card>
      )}

      <Card padding="sm">
        <h2 className={rs.sectionTitle}>Kind-Läufe</h2>
        <ResearchTableFrame>
          <table className={rs.table}>
            <thead>
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
                  <th key={col} className={`whitespace-nowrap ${rs.th}`}>
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
                  <td className={`${rs.td} font-mono text-[11px]`}>{child.child_id}</td>
                  <td className={`${rs.td} font-mono text-[11px]`}>
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
                  <td className={rs.td}>{displayValue(child.status)}</td>
                  <td className={`${rs.td} font-mono`}>{displayValue(child.net_pnl)}</td>
                  <td className={`${rs.td} font-mono`}>
                    {displayValue(child.max_drawdown)}
                  </td>
                  <td className={`${rs.td} font-mono`}>
                    {child.closed_trades == null ? "Nicht verfügbar" : child.closed_trades}
                  </td>
                  <td className={`${rs.td} text-[11px] text-red-300`}>
                    {displayValue(child.error)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ResearchTableFrame>
      </Card>
    </div>
  );
}
