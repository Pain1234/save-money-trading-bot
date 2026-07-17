"use client";

import { READ_ONLY_BANNER } from "@/lib/dashboard/constants";
import type { QuickStatVm } from "@/lib/dashboard/types";
import {
  Card,
  NumberInput,
  PanelHeader,
  Select,
  Toggle,
} from "@/components/ui/Card";

const RISK_LABELS = [
  { id: "r1", label: "Risiko pro Trade", value: "—", suffix: "%" },
  { id: "r2", label: "Max. Gesamtrisiko", value: "—", suffix: "%" },
  { id: "r3", label: "Max. Positionen", value: "—" },
  { id: "r4", label: "ATR Stop Multiplier", value: "—", suffix: "x" },
  { id: "r5", label: "ATR Target Multiplier", value: "—", suffix: "x" },
];

const FILTER_LABELS = [
  { id: "f1", label: "Volumen Filter" },
  { id: "f2", label: "Fear & Greed Filter" },
  { id: "f3", label: "Makro Filter" },
];

function ReadOnlyBanner() {
  return (
    <p
      className="mb-2 rounded-[6px] border border-border bg-bg-card-alt px-2 py-1 text-[10px] leading-snug text-text-muted"
      data-testid="readonly-banner"
    >
      {READ_ONLY_BANNER}
    </p>
  );
}

export function BotControls() {
  return (
    <Card padding="sm" className="control-panel flex min-w-0 flex-col">
      <PanelHeader title="Bot Steuerung" compact />
      <ReadOnlyBanner />

      <div className="flex flex-1 flex-col justify-between gap-2">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <span className="text-[12px] text-text-secondary">Aktiv</span>
          <Toggle
            enabled={false}
            disabled
            label="Bot aktiv (nicht verfügbar)"
            small
          />
        </div>

        <div className="space-y-1">
          <button
            type="button"
            disabled
            aria-disabled="true"
            data-testid="bot-start-button"
            className="w-full cursor-not-allowed rounded-[6px] bg-mint/40 px-2 py-1.5 text-[12px] font-medium text-bg-base opacity-60"
          >
            Bot starten (nicht verfügbar)
          </button>
          <button
            type="button"
            disabled
            aria-disabled="true"
            data-testid="bot-pause-button"
            className="w-full cursor-not-allowed rounded-[6px] border border-warning/40 px-2 py-1.5 text-[12px] text-warning opacity-60"
          >
            Bot pausieren (nicht verfügbar)
          </button>
          <button
            type="button"
            disabled
            aria-disabled="true"
            data-testid="bot-stop-button"
            className="w-full cursor-not-allowed rounded-[6px] border border-negative/40 px-2 py-1.5 text-[12px] text-negative opacity-60"
          >
            Bot stoppen (nicht verfügbar)
          </button>
        </div>

        <div className="min-w-0">
          <label className="mb-1 block text-[11px] text-text-muted">
            Trading Modus
          </label>
          <Select
            value="Paper Monitoring"
            options={["Paper Monitoring"]}
            disabled
          />
        </div>
      </div>
    </Card>
  );
}

export function RiskManagement() {
  return (
    <Card padding="sm" className="control-panel flex min-w-0 flex-col">
      <PanelHeader title="Risikomanagement" compact />
      <ReadOnlyBanner />

      <div className="flex flex-1 flex-col justify-between gap-1">
        {RISK_LABELS.map((setting) => (
          <div
            key={setting.id}
            className="flex min-w-0 items-center justify-between gap-2 py-0.5"
          >
            <span className="min-w-0 text-[12px] text-text-secondary">
              {setting.label}
            </span>
            <NumberInput
              value={setting.value}
              suffix={setting.suffix}
              disabled
            />
          </div>
        ))}
        <div className="flex min-w-0 items-center justify-between gap-2 py-0.5">
          <span className="min-w-0 text-[12px] text-text-secondary">
            Trailing Stop
          </span>
          <Toggle enabled={false} disabled label="Trailing Stop" small />
        </div>
      </div>
    </Card>
  );
}

export function FilterSettings() {
  return (
    <Card padding="sm" className="control-panel flex min-w-0 flex-col" id="einstellungen">
      <PanelHeader title="Filter Einstellungen" compact />
      <ReadOnlyBanner />

      <div className="flex flex-1 flex-col justify-between gap-0.5">
        {FILTER_LABELS.map((filter) => (
          <div key={filter.id} className="min-w-0 py-0.5">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="min-w-0 text-[12px] leading-tight text-text-secondary">
                {filter.label}
              </span>
              <Toggle
                enabled={false}
                disabled
                label={filter.label}
                small
              />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function QuickStats({ stats }: { stats: QuickStatVm[] }) {
  return (
    <Card padding="sm" className="control-panel flex min-w-0 flex-col">
      <PanelHeader title="Schnellstatistiken" compact />

      <div className="flex min-w-0 flex-1 flex-col justify-between">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="flex min-w-0 items-center justify-between gap-2 border-b border-border/35 py-[5px] last:border-0"
          >
            <span className="min-w-0 shrink text-[11px] leading-tight text-text-muted">
              {stat.label}
            </span>
            <span className="shrink-0 font-mono text-[11px] text-text-primary">
              {stat.value}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function ControlPanels({ quickStats }: { quickStats: QuickStatVm[] }) {
  return (
    <div className="controls-grid" data-testid="control-panels">
      <BotControls />
      <RiskManagement />
      <FilterSettings />
      <QuickStats stats={quickStats} />
    </div>
  );
}
