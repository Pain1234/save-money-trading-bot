import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { StatusBadge } from "@/components/monitor/StatusBadge";
import {
  fetchMarketData,
  fetchStatus,
  getMonitoringErrorMessage,
} from "@/lib/paper-api/client";
export default async function StatusPage() {
  try {
    const [status, marketData] = await Promise.all([fetchStatus(), fetchMarketData()]);
    return (
      <div data-testid="dashboard-page-ready" className="space-y-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">Status & Readiness</h1>
          <StatusBadge status={status.display_status} />
        </div>
        <pre className="overflow-x-auto rounded-xl border border-border-subtle bg-bg-elevated p-4 text-xs">
          {JSON.stringify({ status, marketData }, null, 2)}
        </pre>
      </div>
    );
  } catch (error) {
    return (
      <ErrorPanel
        title="Status unavailable"
        message={getMonitoringErrorMessage(error)}
      />
    );
  }}
