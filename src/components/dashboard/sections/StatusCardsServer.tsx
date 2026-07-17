import { MarketCards } from "@/components/dashboard/MarketCards";
import {
  fetchEvents,
  fetchSchedulerRuns,
  type DashboardSummaryResponse,
  type EventItem,
  type SchedulerRunItem,
} from "@/lib/paper-api/client";
import { formatHeartbeatAge } from "@/lib/dashboard/formatters";
import {
  buildStatusCards,
  isHeartbeatStale,
} from "@/lib/dashboard/view-model";

interface StatusCardsServerProps {
  summary: DashboardSummaryResponse;
}

export async function StatusCardsServer({ summary }: StatusCardsServerProps) {
  const [schedulerResult, eventsResult] = await Promise.allSettled([
    fetchSchedulerRuns(),
    fetchEvents(),
  ]);

  const schedulerRuns: SchedulerRunItem[] =
    schedulerResult.status === "fulfilled" ? schedulerResult.value.items : [];
  const events: EventItem[] =
    eventsResult.status === "fulfilled" ? eventsResult.value.items : [];

  const cards = buildStatusCards({
    displayStatus: summary.display_status,
    readinessOk: summary.readiness.runtime_readiness,
    readinessReasons: summary.readiness.reasons,
    stale: isHeartbeatStale(summary),
    heartbeatAge: formatHeartbeatAge(summary.status.heartbeat_age_seconds),
    schedulerRuns,
    events,
  });
  return <MarketCards cards={cards} />;
}
