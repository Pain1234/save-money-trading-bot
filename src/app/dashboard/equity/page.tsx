import { DataTable } from "@/components/monitor/DataTable";
import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchEquity, getMonitoringErrorMessage } from "@/lib/paper-api/client";
export default async function EquityPage() {
  try {
    const data = await fetchEquity();
    return (
      <DataTable
        title="Equity History"
        columns={["evaluation_time", "equity", "cash"]}
        rows={data.items}
        emptyMessage="No equity snapshots"
      />
    );
  } catch (error) {
    return (
      <ErrorPanel
        title="Equity history unavailable"
        message={getMonitoringErrorMessage(error)}
      />
    );
  }}
