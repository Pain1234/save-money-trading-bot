import { DataTable } from "@/components/monitor/DataTable";
import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchFills } from "@/lib/paper-api/client";

export default async function FillsPage() {
  try {
    const data = await fetchFills();
    return (
      <DataTable
        title="Fills"
        columns={["fill_kind", "symbol", "quantity", "fill_price", "fill_time"]}
        rows={data.items}
        emptyMessage="No fills"
      />
    );
  } catch {
    return <ErrorPanel title="Fills unavailable" />;
  }
}
