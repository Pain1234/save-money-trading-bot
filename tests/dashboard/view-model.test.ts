import { describe, expect, it } from "vitest";

import {
  accentFromSignedDecimal,
  formatDecimalDisplay,
  formatHeartbeatAge,
  formatMoneyDisplay,
  parseDecimalForChart,
} from "../../src/lib/dashboard/formatters";
import {
  buildEquityChartPoints,
  buildFillRows,
  buildPositionRows,
  buildStatusCards,
  buildSummaryViewModel,
  isHeartbeatStale,
} from "../../src/lib/dashboard/view-model";
import type { DashboardSummaryResponse } from "../../src/lib/paper-api/client";

function baseSummary(
  overrides: Partial<DashboardSummaryResponse> = {},
): DashboardSummaryResponse {
  return {
    display_status: "READY",
    status: {
      display_status: "READY",
      heartbeat_age_seconds: 5,
      stale_heartbeat_threshold_seconds: 30,
      hyperliquid_network: "testnet",
      runtime: {
        status: "READY",
        heartbeat_at: "2026-07-17T12:00:00Z",
        last_error: null,
        kill_switch: false,
        paused: false,
      },
      readiness: { runtime_readiness: true, reasons: [] },
    },
    readiness: { runtime_readiness: true, reasons: [] },
    heartbeat_at: "2026-07-17T12:00:00Z",
    wallet: {
      cash: "100000.00",
      total_realized_pnl: "123.45",
      updated_at: "2026-07-17T12:00:00Z",
    },
    open_position_count: 2,
    position_summary: [],
    warnings: [],
    hyperliquid_network: "testnet",
    ...overrides,
  };
}

describe("formatters", () => {
  it("formats decimal strings without inventing values", () => {
    expect(formatDecimalDisplay("1234.5")).toBe("1,234.5");
    expect(formatMoneyDisplay("10.00")).toBe("$10.00");
    expect(formatMoneyDisplay(null)).toBe("—");
    expect(parseDecimalForChart("not-a-number")).toBeNull();
    expect(parseDecimalForChart("12.5")).toBe(12.5);
  });

  it("formats heartbeat age", () => {
    expect(formatHeartbeatAge(12)).toBe("12s");
    expect(formatHeartbeatAge(null)).toBe("unbekannt");
  });

  it("derives accent from decimal sign", () => {
    expect(accentFromSignedDecimal("12.5")).toBe("mint");
    expect(accentFromSignedDecimal("-3.25")).toBe("danger");
    expect(accentFromSignedDecimal(null)).toBe("default");
    expect(accentFromSignedDecimal("-0.00")).toBe("mint");
  });
});

describe("buildSummaryViewModel", () => {
  it("maps summary into KPI view models", () => {
    const vm = buildSummaryViewModel(baseSummary());
    expect(vm.kpis.find((k) => k.id === "balance")?.label).toBe("Cash");
    expect(vm.kpis.find((k) => k.id === "balance")?.value).toBe("$100,000.00");
    expect(vm.kpis.find((k) => k.id === "pnl")?.label).toBe("Realized PnL");
    expect(vm.kpis.find((k) => k.id === "pnl")?.accent).toBe("mint");
    expect(vm.kpis.find((k) => k.id === "positions")?.value).toBe("2");
    expect(vm.kpis.find((k) => k.id === "winrate")?.value).toBe(
      "Nicht verfügbar",
    );
  });

  it("does not crash when wallet is null", () => {
    const vm = buildSummaryViewModel(baseSummary({ wallet: null }));
    expect(vm.kpis.find((k) => k.id === "balance")?.value).toBe("—");
    expect(vm.kpis.find((k) => k.id === "pnl")?.value).toBe("—");
    expect(vm.kpis.find((k) => k.id === "pnl")?.accent).toBe("default");
  });

  it("marks negative realized pnl with danger accent", () => {
    const vm = buildSummaryViewModel(
      baseSummary({
        wallet: {
          cash: "90000.00",
          total_realized_pnl: "-42.50",
          updated_at: "2026-07-17T12:00:00Z",
        },
      }),
    );
    expect(vm.kpis.find((k) => k.id === "pnl")?.accent).toBe("danger");
    expect(vm.kpis.find((k) => k.id === "pnl")?.value).toMatch(/-/);
  });

  it("marks stale heartbeat", () => {
    const summary = baseSummary({
      status: {
        ...baseSummary().status,
        heartbeat_age_seconds: 120,
        stale_heartbeat_threshold_seconds: 30,
      },
    });
    expect(isHeartbeatStale(summary)).toBe(true);
    const vm = buildSummaryViewModel(summary);
    expect(vm.staleHeartbeat).toBe(true);
    expect(vm.kpis.find((k) => k.id === "status")?.subValue).toMatch(/veraltet/i);
  });

  it("shows unavailable for kill switch and paused when runtime is null", () => {
    const vm = buildSummaryViewModel(
      baseSummary({
        display_status: "STOPPED",
        status: {
          ...baseSummary().status,
          display_status: "STOPPED",
          runtime: null,
        },
      }),
    );
    expect(vm.quickStats.find((s) => s.label === "Kill Switch")?.value).toBe(
      "Nicht verfügbar",
    );
    expect(vm.quickStats.find((s) => s.label === "Paused")?.value).toBe(
      "Nicht verfügbar",
    );
  });
});

describe("buildStatusCards", () => {
  it("distinguishes empty success from endpoint errors", () => {
    const okEmpty = buildStatusCards({
      displayStatus: "READY",
      readinessOk: true,
      readinessReasons: [],
      stale: false,
      heartbeatAge: "4s",
      scheduler: { status: "ok", items: [] },
      events: { status: "ok", items: [] },
    });
    expect(okEmpty.find((c) => c.id === "scheduler")?.value).toBe("Keine Läufe");
    expect(okEmpty.find((c) => c.id === "incidents")?.value).toBe(
      "0 in letzten 50 Events",
    );

    const errored = buildStatusCards({
      displayStatus: "READY",
      readinessOk: true,
      readinessReasons: [],
      stale: false,
      heartbeatAge: "4s",
      scheduler: { status: "error" },
      events: { status: "error" },
    });
    expect(errored.find((c) => c.id === "scheduler")?.value).toBe(
      "Nicht verfügbar",
    );
    expect(errored.find((c) => c.id === "incidents")?.value).toBe(
      "Nicht verfügbar",
    );
  });
});

describe("positions and fills", () => {
  it("always uses LONG side from V1 contract", () => {
    const rows = buildPositionRows([
      {
        position_id: "p1",
        symbol: "BTC",
        status: "OPEN",
        quantity: "0.5",
        average_entry_price: "60000",
        current_stop: "58000",
        unrealized_pnl: "10",
        opened_at: "2026-07-17T12:00:00Z",
      },
    ]);
    expect(rows[0]?.side).toBe("long");
    expect(rows[0]?.markPriceDisplay).toBe("—");
    expect(rows[0]?.takeProfitDisplay).toBe("—");
  });

  it("maps empty positions to empty rows", () => {
    expect(buildPositionRows([])).toEqual([]);
  });

  it("maps fills without R-multiple", () => {
    const rows = buildFillRows([
      {
        fill_id: "f1",
        fill_kind: "ENTRY",
        symbol: "ETH",
        quantity: "1",
        fill_price: "3000",
        fill_time: "2026-07-17T12:00:00Z",
      },
    ]);
    expect(rows[0]?.fillKind).toBe("ENTRY");
    expect(rows[0]).not.toHaveProperty("rMultiple");
  });
});

describe("equity chart", () => {
  it("sorts chronologically and skips invalid points", () => {
    const points = buildEquityChartPoints([
      { evaluation_time: "2026-07-02T00:00:00Z", equity: "200", cash: "200" },
      { evaluation_time: "2026-07-01T00:00:00Z", equity: "100", cash: "100" },
      { evaluation_time: "2026-07-03T00:00:00Z", equity: null, cash: "0" },
    ]);
    expect(points).toHaveLength(2);
    expect(points[0]?.equity).toBe(100);
    expect(points[1]?.equity).toBe(200);
  });

  it("returns empty list for empty history", () => {
    expect(buildEquityChartPoints([])).toEqual([]);
  });

  it("parses scientific equity strings for the Overview/Equity chart path", () => {
    const points = buildEquityChartPoints([
      {
        evaluation_time: "2026-07-01T00:00:00Z",
        equity: "0E-18",
        cash: "0",
      },
      {
        evaluation_time: "2026-07-02T00:00:00Z",
        equity: "100000.000000",
        cash: "100000",
      },
    ]);
    expect(points).toHaveLength(2);
    expect(points[0]?.equity).toBe(0);
    expect(points[1]?.equity).toBe(100000);
  });
});
