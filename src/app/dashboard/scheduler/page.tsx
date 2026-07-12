import { DataTable } from "@/components/monitor/DataTable";
import { ErrorPanel } from "@/components/monitor/ErrorPanel";
import { fetchSchedulerRuns } from "@/lib/paper-api/client";

export default async function SchedulerPage() {
  try {
    const data = await fetchSchedulerRuns();
    return (
      <DataTable
        title="Scheduler Runs"
        columns={["job_name", "status", "scheduled_for", "error"]}
        rows={data.items}
        emptyMessage="No scheduler runs"
      />
    );
  } catch {
    return <ErrorPanel title="Scheduler runs unavailable" />;
  }
}
