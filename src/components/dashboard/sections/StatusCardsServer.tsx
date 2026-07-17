import { MarketCards } from "@/components/dashboard/MarketCards";
import {
  fetchEvents,
  fetchSchedulerRuns,
  type DashboardSummaryResponse,
} from "@/lib/paper-api/client";
import { formatHeartbeatAge } from "@/lib/dashboard/formatters";
import {
  buildStatusCards,
  isHeartbeatStale,
  type SectionFetchState,
} from "@/lib/dashboard/view-model";
import type { EventItem, SchedulerRunItem } from "@/lib/paper-api/client";

interface StatusCardsServerProps {
  summary: DashboardSummaryResponse;
}

function toSectionState<T>(
  result: PromiseSettledResult<{ items: T[] }>,
): SectionFetchState<T> {
  if (result.status === "fulfilled") {
    return { status: "ok", items: result.value.items };
  }
  return { status: "error" };
}

export async function StatusCardsServer({ summary }: StatusCardsServerProps) {
  const [schedulerResult, eventsResult] = await Promise.allSettled([
    fetchSchedulerRuns(),
    fetchEvents(),
  ]);

  const scheduler: SectionFetchState<SchedulerRunItem> =
    toSectionState(schedulerResult);
  const events: SectionFetchState<EventItem> = toSectionState(eventsResult);

  const cards = buildStatusCards({
    displayStatus: summary.display_status,
    readinessOk: summary.readiness.runtime_readiness,
    readinessReasons: summary.readiness.reasons,
    stale: isHeartbeatStale(summary),
    heartbeatAge: formatHeartbeatAge(summary.status.heartbeat_age_seconds),
    scheduler,
    events,
  });
  return <MarketCards cards={cards} />;
}
