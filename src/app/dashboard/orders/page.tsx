import { DataTable } from "@/components/monitor/DataTable";
import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchOrders } from "@/lib/paper-api/client";

export default async function OrdersPage() {
  try {
    const data = await fetchOrders();
    return (
      <DataTable
        title="Orders"
        columns={["symbol", "status", "requested_quantity", "expected_fill_time"]}
        rows={data.items}
        emptyMessage="No orders"
      />
    );
  } catch {
    return <ErrorPanel title="Orders unavailable" />;
  }
}
