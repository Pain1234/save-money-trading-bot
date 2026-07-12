import { DataTable } from "@/components/monitor/DataTable";
import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchPositions, getMonitoringErrorMessage } from "@/lib/paper-api/client";
export default async function PositionsPage() {
  try {
    const data = await fetchPositions();
    return (
      <DataTable
        title="Positions"
        columns={["symbol", "status", "quantity", "average_entry_price", "current_stop", "opened_at"]}
        rows={data.items}
        emptyMessage="No positions"
      />
    );
  } catch (error) {
    return (
      <ErrorPanel
        title="Positions unavailable"
        message={getMonitoringErrorMessage(error)}
      />
    );
  }}
