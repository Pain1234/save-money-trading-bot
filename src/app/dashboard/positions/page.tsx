import { DataTable } from "@/components/monitor/DataTable";
import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchPositions } from "@/lib/paper-api/client";

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
  } catch {
    return <ErrorPanel title="Positions unavailable" />;
  }
}
