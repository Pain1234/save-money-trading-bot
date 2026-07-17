import { FillsTable } from "@/components/dashboard/Tables";
import {
  fetchFills,
  getMonitoringErrorMessage,
} from "@/lib/paper-api/client";
import { buildFillRows } from "@/lib/dashboard/view-model";

export async function FillsTableServer() {
  try {
    const page = await fetchFills();
    const rows = buildFillRows(page.items.slice(0, 10));
    return <FillsTable rows={rows} />;
  } catch (error) {
    return (
      <FillsTable rows={[]} errorMessage={getMonitoringErrorMessage(error)} />
    );
  }
}
