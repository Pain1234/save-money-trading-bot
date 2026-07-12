import { DataTable } from "@/components/monitor/DataTable";
import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchEvents } from "@/lib/paper-api/client";

export default async function IncidentsPage() {
  try {
    const data = await fetchEvents();
    const incidents = data.items.filter((event) =>
      /FAIL|ERROR|KILL|REJECT|ORPHAN/i.test(event.event_type),
    );
    return (
      <DataTable
        title="Errors / Incidents"
        columns={["event_type", "aggregate_type", "created_at"]}
        rows={incidents.length > 0 ? incidents : data.items.slice(0, 20)}
        emptyMessage="No incidents recorded"
      />
    );
  } catch {
    return <ErrorPanel title="Incidents unavailable" />;
  }
}
