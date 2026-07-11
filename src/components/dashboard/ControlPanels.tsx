"use client";

import {
  BOT_CONTROLS,
  FILTER_SETTINGS,
  QUICK_STATS,
  RISK_SETTINGS,
} from "@/lib/mock-data";
import {
  Card,
  NumberInput,
  PanelHeader,
  Select,
  Toggle,
} from "@/components/ui/Card";
import { useState } from "react";

export function BotControls() {
  const [active, setActive] = useState(BOT_CONTROLS.isActive);

  return (
    <Card padding="sm" className="control-panel flex min-w-0 flex-col">
      <PanelHeader title="Bot Steuerung" compact />

      <div className="flex flex-1 flex-col justify-between gap-2">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <span className="text-[12px] text-text-secondary">Aktiv</span>
          <Toggle enabled={active} onChange={setActive} label="Bot aktiv" small />
        </div>

        <div className="space-y-1">
          <button
            type="button"
            className="w-full rounded-[6px] bg-mint px-2 py-1.5 text-[12px] font-medium text-bg-base hover:opacity-90"
          >
            Bot starten
          </button>
          <button
            type="button"
            className="w-full rounded-[6px] border border-warning/40 px-2 py-1.5 text-[12px] text-warning hover:bg-warning/5"
          >
            Bot pausieren
          </button>
          <button
            type="button"
            className="w-full rounded-[6px] border border-negative/40 px-2 py-1.5 text-[12px] text-negative hover:bg-negative/5"
          >
            Bot stoppen
          </button>
        </div>

        <div className="min-w-0">
          <label className="mb-1 block text-[11px] text-text-muted">
            Trading Modus
          </label>
          <Select
            value={BOT_CONTROLS.tradingMode}
            options={["Automatisch", "Semi-Automatisch", "Manuell"]}
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

      <div className="flex flex-1 flex-col justify-between gap-1">
        {RISK_SETTINGS.map((setting) =>
          setting.type === "toggle" ? (
            <div
              key={setting.id}
              className="flex min-w-0 items-center justify-between gap-2 py-0.5"
            >
              <span className="min-w-0 text-[12px] text-text-secondary">
                {setting.label}
              </span>
              <Toggle enabled={setting.enabled ?? false} label={setting.label} small />
            </div>
          ) : (
            <div
              key={setting.id}
              className="flex min-w-0 items-center justify-between gap-2 py-0.5"
            >
              <span className="min-w-0 text-[12px] text-text-secondary">
                {setting.label}
              </span>
              <NumberInput value={setting.value ?? ""} suffix={setting.suffix} />
            </div>
          ),
        )}
      </div>
    </Card>
  );
}

export function FilterSettings() {
  return (
    <Card padding="sm" className="control-panel flex min-w-0 flex-col" id="einstellungen">
      <PanelHeader title="Filter Einstellungen" compact />

      <div className="flex flex-1 flex-col justify-between gap-0.5">
        {FILTER_SETTINGS.map((filter) => (
          <div key={filter.id} className="min-w-0 py-0.5">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="min-w-0 text-[12px] leading-tight text-text-secondary">
                {filter.label}
              </span>
              <Toggle enabled={filter.enabled} label={filter.label} small />
            </div>
            {filter.hasInput && filter.enabled && (
              <div className="mt-0.5 flex justify-end">
                <NumberInput value={filter.value?.replace("≥ ", "") ?? "25"} />
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

export function QuickStats() {
  return (
    <Card padding="sm" className="control-panel flex min-w-0 flex-col">
      <PanelHeader title="Schnellstatistiken" compact />

      <div className="flex min-w-0 flex-1 flex-col justify-between">
        {QUICK_STATS.map((stat) => (
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

export function ControlPanels() {
  return (
    <div className="controls-grid">
      <BotControls />
      <RiskManagement />
      <FilterSettings />
      <QuickStats />
    </div>
  );
}
