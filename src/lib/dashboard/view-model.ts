import type {
  DashboardSummaryResponse,
  EquityPoint,
  EventItem,
  FillItem,
  PositionItem,
  SchedulerRunItem,
} from "@/lib/paper-api/client";
import {
  UNAVAILABLE,
  accentFromSignedDecimal,
  coinColor,
  coinInitial,
  formatDecimalDisplay,
  formatHeartbeatAge,
  formatIsoDateTime,
  formatMoneyDisplay,
  parseDecimalForChart,
} from "@/lib/dashboard/formatters";
import type {
  EquityChartPointVm,
  FillRowVm,
  PositionRowVm,
  QuickStatVm,
  StatusCardVm,
  SummaryViewModel,
} from "@/lib/dashboard/types";

export function isHeartbeatStale(summary: DashboardSummaryResponse): boolean {
  const age = summary.status.heartbeat_age_seconds;
  const threshold = summary.status.stale_heartbeat_threshold_seconds;
  return age != null && age > threshold;
}

function runtimeFlagLabel(
  runtime: DashboardSummaryResponse["status"]["runtime"],
  flag: "kill_switch" | "paused",
  whenTrue: string,
  whenFalse: string,
): string {
  if (runtime == null) return "Nicht verfügbar";
  return runtime[flag] ? whenTrue : whenFalse;
}

export function buildSummaryViewModel(
  summary: DashboardSummaryResponse,
): SummaryViewModel {
  const stale = isHeartbeatStale(summary);
  const wallet = summary.wallet;
  const statusValue = summary.display_status;
  const ageLabel = formatHeartbeatAge(summary.status.heartbeat_age_seconds);
  const runtime = summary.status.runtime;

  const kpis = [
    {
      id: "balance",
      label: "Cash",
      value: wallet ? formatMoneyDisplay(wallet.cash) : UNAVAILABLE,
      subValue: wallet
        ? `Stand ${formatIsoDateTime(wallet.updated_at)}`
        : "Wallet-Daten nicht verfügbar",
      accent: "default" as const,
    },
    {
      id: "status",
      label: "Bot Status",
      value: statusValue,
      subValue: stale
        ? `Heartbeat veraltet (${ageLabel})`
        : `Heartbeat ${ageLabel}`,
      accent: (stale || statusValue === "DEGRADED"
        ? "warning"
        : statusValue === "STOPPED"
          ? "danger"
          : "mint") as "warning" | "danger" | "mint",
      large: true,
    },
    {
      id: "pnl",
      label: "Realized PnL",
      value: wallet
        ? formatMoneyDisplay(wallet.total_realized_pnl)
        : UNAVAILABLE,
      subValue: "Gesamt (Wallet)",
      accent: wallet
        ? accentFromSignedDecimal(wallet.total_realized_pnl)
        : ("default" as const),
    },
    {
      id: "positions",
      label: "Offene Positionen",
      value: String(summary.open_position_count),
      subValue:
        summary.warnings.length > 0
          ? `${summary.warnings.length} Warnung(en)`
          : summary.readiness.runtime_readiness
            ? "Runtime bereit"
            : "Runtime nicht bereit",
      accent: "default" as const,
    },
    {
      id: "winrate",
      label: "Win Rate",
      value: "Nicht verfügbar",
      subValue: "Kein API-Feld in V1",
      accent: "default" as const,
    },
    {
      id: "profitfactor",
      label: "Profit Faktor",
      value: "Nicht verfügbar",
      subValue: "Kein API-Feld in V1",
      accent: "default" as const,
    },
  ];

  const quickStats: QuickStatVm[] = [
    { label: "Network", value: summary.hyperliquid_network || UNAVAILABLE },
    {
      label: "Readiness",
      value: summary.readiness.runtime_readiness ? "OK" : "Nein",
    },
    {
      label: "Offene Positionen",
      value: String(summary.open_position_count),
    },
    {
      label: "Warnungen",
      value: String(summary.warnings.length),
    },
    {
      label: "Kill Switch",
      value: runtimeFlagLabel(runtime, "kill_switch", "AN", "AUS"),
    },
    {
      label: "Paused",
      value: runtimeFlagLabel(runtime, "paused", "Ja", "Nein"),
    },
  ];

  return {
    kpis,
    quickStats,
    staleHeartbeat: stale,
    warnings: summary.warnings,
  };
}

/** Map open positions. Side is always LONG per V1 PaperSide contract. */
export function buildPositionRows(items: PositionItem[]): PositionRowVm[] {
  return items.map((p) => ({
    id: p.position_id,
    symbol: p.symbol,
    coin: coinInitial(p.symbol),
    coinColor: coinColor(p.symbol),
    side: "long",
    sizeDisplay: formatDecimalDisplay(p.quantity),
    entryPriceDisplay: formatMoneyDisplay(p.average_entry_price),
    markPriceDisplay: UNAVAILABLE,
    pnlDisplay: formatMoneyDisplay(p.unrealized_pnl),
    pnlNumericHint: parseDecimalForChart(p.unrealized_pnl),
    riskDisplay: UNAVAILABLE,
    stopLossDisplay: formatMoneyDisplay(p.current_stop),
    takeProfitDisplay: UNAVAILABLE,
  }));
}

export function buildFillRows(items: FillItem[]): FillRowVm[] {
  return items.map((f) => ({
    id: f.fill_id,
    symbol: f.symbol,
    coin: coinInitial(f.symbol),
    coinColor: coinColor(f.symbol),
    fillKind: f.fill_kind,
    quantityDisplay: formatDecimalDisplay(f.quantity),
    priceDisplay: formatMoneyDisplay(f.fill_price),
    timeDisplay: formatIsoDateTime(f.fill_time),
  }));
}

export function buildEquityChartPoints(
  items: EquityPoint[],
): EquityChartPointVm[] {
  const sorted = [...items].sort((a, b) => {
    const ta = a.evaluation_time ?? "";
    const tb = b.evaluation_time ?? "";
    return ta.localeCompare(tb);
  });

  return sorted
    .map((point) => {
      const equityNum = parseDecimalForChart(point.equity);
      if (equityNum == null || point.equity == null) return null;
      return {
        label: point.evaluation_time
          ? formatIsoDateTime(point.evaluation_time)
          : "",
        equity: equityNum,
        equityRaw: point.equity,
        evaluationTime: point.evaluation_time,
      };
    })
    .filter((p): p is EquityChartPointVm => p != null);
}

export function filterEquityByPeriod(
  points: EquityChartPointVm[],
  period: string,
): EquityChartPointVm[] {
  if (period === "All" || points.length === 0) return points;
  const last = points[points.length - 1];
  if (!last?.evaluationTime) return points;
  const end = new Date(last.evaluationTime).getTime();
  if (Number.isNaN(end)) return points;
  const dayMs = 24 * 60 * 60 * 1000;
  const windowMs: Record<string, number> = {
    "1D": dayMs,
    "7D": 7 * dayMs,
    "30D": 30 * dayMs,
    "90D": 90 * dayMs,
    "1Y": 365 * dayMs,
  };
  const window = windowMs[period];
  if (window == null) return points;
  const start = end - window;
  return points.filter((p) => {
    if (!p.evaluationTime) return false;
    const t = new Date(p.evaluationTime).getTime();
    return !Number.isNaN(t) && t >= start;
  });
}

const INCIDENT_RE = /FAIL|ERROR|KILL|REJECT|ORPHAN/i;

export type SectionFetchState<T> =
  | { status: "ok"; items: T[] }
  | { status: "error" };

export function buildStatusCards(input: {
  displayStatus: string;
  readinessOk: boolean;
  readinessReasons: string[];
  stale: boolean;
  heartbeatAge: string;
  scheduler: SectionFetchState<SchedulerRunItem>;
  events: SectionFetchState<EventItem>;
}): StatusCardVm[] {
  const schedulerCard: StatusCardVm =
    input.scheduler.status === "error"
      ? {
          id: "scheduler",
          label: "Scheduler",
          value: "Nicht verfügbar",
          detail: "Scheduler-Endpoint nicht erreichbar",
          tone: "warn",
        }
      : (() => {
          const latestRun = input.scheduler.items[0];
          return {
            id: "scheduler",
            label: "Scheduler",
            value: latestRun?.status ?? "Keine Läufe",
            detail: latestRun
              ? `${latestRun.job_name} · ${formatIsoDateTime(latestRun.scheduled_for)}${
                  latestRun.error ? ` · ${latestRun.error}` : ""
                }`
              : "Keine Scheduler-Daten in den letzten 50 Läufen",
            tone: latestRun?.error ? "danger" : "neutral",
          };
        })();

  const incidentsCard: StatusCardVm =
    input.events.status === "error"
      ? {
          id: "incidents",
          label: "Incidents",
          value: "Nicht verfügbar",
          detail: "Events-Endpoint nicht erreichbar",
          tone: "warn",
        }
      : (() => {
          const incidents = input.events.items.filter((e) =>
            INCIDENT_RE.test(e.event_type),
          );
          const incidentSample = incidents[0] ?? input.events.items[0];
          return {
            id: "incidents",
            label: "Incidents",
            value:
              incidents.length > 0
                ? String(incidents.length)
                : "0 in letzten 50 Events",
            detail: incidentSample
              ? `${incidentSample.event_type} · ${formatIsoDateTime(incidentSample.created_at)}`
              : "Keine Treffer in den letzten 50 Events",
            tone: incidents.length > 0 ? "danger" : "ok",
          };
        })();

  return [
    {
      id: "runtime",
      label: "Monitoring Status",
      value: input.displayStatus,
      detail: input.stale
        ? `Heartbeat veraltet (${input.heartbeatAge})`
        : `Heartbeat ${input.heartbeatAge}`,
      tone: input.stale || input.displayStatus !== "READY" ? "warn" : "ok",
    },
    {
      id: "readiness",
      label: "Readiness",
      value: input.readinessOk ? "Bereit" : "Nicht bereit",
      detail:
        input.readinessReasons.length > 0
          ? input.readinessReasons.slice(0, 2).join("; ")
          : "Keine Gründe",
      tone: input.readinessOk ? "ok" : "warn",
    },
    schedulerCard,
    incidentsCard,
  ];
}
