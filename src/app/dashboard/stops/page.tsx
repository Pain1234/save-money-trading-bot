import { DataTable } from "@/components/monitor/DataTable";
import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchStops, getMonitoringErrorMessage } from "@/lib/paper-api/client";
export default async function StopsPage() {
  try {
    const data = await fetchStops();
    return (
      <DataTable
        title="Stops"
        columns={["position_id", "previous_stop", "new_stop", "evaluation_time", "reason"]}
        rows={data.items}
        emptyMessage="No stop events"
      />
    );
  } catch (error) {
    return (
      <ErrorPanel
        title="Stops unavailable"
        message={getMonitoringErrorMessage(error)}
      />
    );
  }}
