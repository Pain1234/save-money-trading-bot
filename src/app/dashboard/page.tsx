import { StatusBadge } from "@/components/monitor/StatusBadge";
import {
  fetchDashboardSummary,
  getMonitoringErrorMessage,
} from "@/lib/paper-api/client";

function formatAge(seconds: number | null): string {
  if (seconds == null) return "unknown";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

export default async function DashboardOverviewPage() {
  try {
    const summary = await fetchDashboardSummary();
    const status = summary.status;
    const wallet = summary.wallet;
    const stale =
      status.heartbeat_age_seconds != null &&
      status.heartbeat_age_seconds > status.stale_heartbeat_threshold_seconds;

    return (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">Overview</h1>
          <StatusBadge status={summary.display_status} />
        </div>
        {!wallet ? (
          <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
            <p className="font-medium">Wallet data unavailable</p>
            <p className="mt-1 text-text-muted">
              Status and readiness are shown below; wallet metrics will appear when available.
            </p>
          </div>
        ) : null}
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-border-subtle bg-bg-elevated p-4">
            <p className="text-sm text-text-muted">Cash</p>
            <p className="text-xl font-semibold">{wallet?.cash ?? "—"}</p>
          </div>
          <div className="rounded-xl border border-border-subtle bg-bg-elevated p-4">
            <p className="text-sm text-text-muted">Realized PnL</p>
            <p className="text-xl font-semibold">{wallet?.total_realized_pnl ?? "—"}</p>
          </div>
          <div className="rounded-xl border border-border-subtle bg-bg-elevated p-4">
            <p className="text-sm text-text-muted">Last heartbeat age</p>
            <p className={`text-xl font-semibold ${stale ? "text-amber-400" : ""}`}>
              {formatAge(status.heartbeat_age_seconds)}
            </p>
            {stale ? (
              <p className="mt-1 text-xs text-amber-400">Heartbeat is stale</p>
            ) : null}
          </div>
        </div>
        {summary.warnings.length > 0 ? (
          <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
            <p className="font-medium">Readiness notes</p>
            <ul className="mt-2 list-disc pl-5">
              {summary.warnings.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  } catch (error) {
    return (
      <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-6">
        <h1 className="text-xl font-semibold text-red-300">API Error</h1>
        <p className="mt-2 text-sm">{getMonitoringErrorMessage(error)}</p>
      </div>
    );
  }
}
