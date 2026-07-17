import { PositionsTable } from "@/components/dashboard/Tables";
import {
  fetchOpenPositions,
  getMonitoringErrorMessage,
} from "@/lib/paper-api/client";
import { buildPositionRows } from "@/lib/dashboard/view-model";

export async function PositionsTableServer() {
  try {
    const page = await fetchOpenPositions();
    const rows = buildPositionRows(page.items);
    return <PositionsTable rows={rows} />;
  } catch (error) {
    return (
      <PositionsTable
        rows={[]}
        errorMessage={getMonitoringErrorMessage(error)}
      />
    );
  }
}
