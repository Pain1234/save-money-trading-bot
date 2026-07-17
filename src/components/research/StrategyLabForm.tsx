"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/Card";

export interface StrategyOption {
  strategy_id: string;
  strategy_version: string;
  label: string;
  timeframes: string[];
  timeframe_note: string;
  symbols: string[];
}

export interface DatasetOption {
  id: string;
  label: string;
  dataset_id: string;
  symbols: string[];
}

export interface StrategySchemaPayload {
  strategy_id: string;
  strategy_version: string;
  parameter_defaults: Record<string, unknown>;
  parameters_schema: {
    properties?: Record<string, { type?: string | string[]; default?: unknown }>;
  };
  symbols: string[];
  timeframes: string[];
}

interface StrategyLabFormProps {
  strategies: StrategyOption[];
  datasets: DatasetOption[];
  initialSchema: StrategySchemaPayload | null;
}

type Step = "form" | "summary";

export function StrategyLabForm({
  strategies,
  datasets,
  initialSchema,
}: StrategyLabFormProps) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("form");
  const [strategyId, setStrategyId] = useState(
    strategies[0]?.strategy_id ?? "trend_v1",
  );
  const [schema, setSchema] = useState<StrategySchemaPayload | null>(initialSchema);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [symbols, setSymbols] = useState<string[]>(
    datasets[0]?.symbols?.length ? [datasets[0].symbols[0]] : ["BTC"],
  );
  const [datasetId, setDatasetId] = useState(datasets[0]?.id ?? "");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-01-31");
  const [timeframe, setTimeframe] = useState("1D");
  const [capital, setCapital] = useState("100000");
  const [entryFee, setEntryFee] = useState("0.0005");
  const [exitFee, setExitFee] = useState("0.0005");
  const [slippageBps, setSlippageBps] = useState("5");
  const [seed, setSeed] = useState("42");
  const [parameters, setParameters] = useState<Record<string, string>>(() => {
    const defaults = initialSchema?.parameter_defaults ?? {};
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(defaults)) {
      if (k === "strategy_version") continue;
      out[k] = String(v);
    }
    return out;
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const strategy = strategies.find((s) => s.strategy_id === strategyId);

  const paramKeys = useMemo(() => {
    const props = schema?.parameters_schema?.properties ?? {};
    return Object.keys(props).filter((k) => k !== "strategy_version");
  }, [schema]);

  async function onStrategyChange(next: string) {
    setStrategyId(next);
    setFieldErrors({});
    const resp = await fetch(
      `/api/research/strategies/${encodeURIComponent(next)}/schema`,
    );
    if (!resp.ok) {
      setFormError("Strategie-Schema konnte nicht geladen werden");
      return;
    }
    const body = (await resp.json()) as StrategySchemaPayload;
    setSchema(body);
    const nextParams: Record<string, string> = {};
    for (const [k, v] of Object.entries(body.parameter_defaults ?? {})) {
      if (k === "strategy_version") continue;
      nextParams[k] = String(v);
    }
    setParameters(nextParams);
  }

  function validateLocal(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = "Experimentname ist erforderlich";
    if (!datasetId) errors.dataset_catalog_id = "Dataset ist erforderlich";
    if (!symbols.length) errors.symbols = "Mindestens ein Symbol wählen";
    if (!startDate || !endDate) errors.time_range = "Zeitraum erforderlich";
    if (startDate && endDate && startDate >= endDate) {
      errors.time_range = "Startdatum muss vor Enddatum liegen";
    }
    if (!(Number(capital) > 0)) errors.starting_capital = "Startkapital muss positiv sein";
    if (Number(entryFee) < 0 || Number(exitFee) < 0) {
      errors.fee_assumption = "Gebühren dürfen nicht negativ sein";
    }
    if (Number(slippageBps) < 0) {
      errors.slippage_assumption = "Slippage darf nicht negativ sein";
    }
    return errors;
  }

  function buildPayload() {
    const paramPayload: Record<string, unknown> = {
      strategy_version: strategy?.strategy_version ?? schema?.strategy_version,
    };
    for (const [k, v] of Object.entries(parameters)) {
      paramPayload[k] = v;
    }
    return {
      strategy_id: strategyId,
      strategy_version: strategy?.strategy_version ?? schema?.strategy_version,
      name: name.trim(),
      notes,
      symbols,
      timeframe,
      time_range: {
        start: `${startDate}T00:00:00.000000Z`,
        end: `${endDate}T23:59:59.999999Z`,
      },
      starting_capital: capital,
      parameters: paramPayload,
      fee_assumption: {
        entry_fee_rate: entryFee,
        exit_fee_rate: exitFee,
      },
      slippage_assumption: {
        slippage_bps: slippageBps,
      },
      random_seed: seed === "" ? null : Number(seed),
      dataset_catalog_id: datasetId,
      owner: "dashboard",
    };
  }

  function goSummary() {
    const errors = validateLocal();
    setFieldErrors(errors);
    setFormError(null);
    if (Object.keys(errors).length) return;
    setStep("summary");
  }

  async function createAndStart() {
    const errors = validateLocal();
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      setStep("form");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const createResp = await fetch("/api/research/experiments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const createBody = await createResp.json();
      if (!createResp.ok) {
        const fields = createBody?.detail?.fields ?? {};
        setFieldErrors(fields);
        setFormError(createBody?.detail?.message ?? "Erstellen fehlgeschlagen");
        setStep("form");
        return;
      }
      const experimentId = createBody.experiment_id as string;
      const startResp = await fetch(
        `/api/research/experiments/${encodeURIComponent(experimentId)}/start`,
        { method: "POST" },
      );
      if (!startResp.ok) {
        const startBody = await startResp.json();
        setFormError(
          startBody?.detail?.message ?? "Start fehlgeschlagen",
        );
        router.push(
          `/dashboard/research/experiments/${encodeURIComponent(experimentId)}`,
        );
        return;
      }
      router.push(
        `/dashboard/research/experiments/${encodeURIComponent(experimentId)}`,
      );
    } catch {
      setFormError("Netzwerkfehler beim Erstellen/Starten");
    } finally {
      setSubmitting(false);
    }
  }

  if (!strategies.length) {
    return (
      <div data-testid="research-lab-empty">
        <p className="text-sm text-text-muted">Keine Strategien registriert.</p>
      </div>
    );
  }

  if (!datasets.length) {
    return (
      <div data-testid="research-lab-no-datasets" className="space-y-2">
        <h1 className="text-2xl font-semibold">Neues Experiment</h1>
        <p className="text-sm text-text-muted">
          Kein Dataset-Katalog konfiguriert. Setzen Sie{" "}
          <code className="font-mono text-xs">RESEARCH_DATASET_CATALOG_PATH</code>{" "}
          (oder JSON-Env) auf der Research API — freie Dateipfade vom Client sind
          nicht erlaubt.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="research-lab-ready" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Neues Experiment</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Strategy Lab — konfiguriert denselben ExperimentSpec / Runner wie die CLI.
          </p>
        </div>
      </div>

      {formError && (
        <p
          className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200"
          data-testid="research-lab-error"
        >
          {formError}
        </p>
      )}

      {step === "form" ? (
        <Card padding="sm" className="space-y-4">
          <label className="block text-sm">
            <span className="text-text-muted">Strategie</span>
            <select
              className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5"
              value={strategyId}
              onChange={(e) => void onStrategyChange(e.target.value)}
              data-testid="lab-strategy"
            >
              {strategies.map((s) => (
                <option key={s.strategy_id} value={s.strategy_id}>
                  {s.label} ({s.strategy_version})
                </option>
              ))}
            </select>
            {fieldErrors.strategy_id && (
              <span className="text-xs text-red-300">{fieldErrors.strategy_id}</span>
            )}
          </label>

          <label className="block text-sm">
            <span className="text-text-muted">Experimentname</span>
            <input
              className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5"
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="lab-name"
            />
            {fieldErrors.name && (
              <span className="text-xs text-red-300">{fieldErrors.name}</span>
            )}
          </label>

          <label className="block text-sm">
            <span className="text-text-muted">Notiz (optional)</span>
            <textarea
              className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
          </label>

          <label className="block text-sm">
            <span className="text-text-muted">Dataset</span>
            <select
              className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5"
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              data-testid="lab-dataset"
            >
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
            {fieldErrors.dataset_catalog_id && (
              <span className="text-xs text-red-300">
                {fieldErrors.dataset_catalog_id}
              </span>
            )}
          </label>

          <fieldset className="text-sm">
            <legend className="text-text-muted">Symbole</legend>
            <div className="mt-1 flex flex-wrap gap-3">
              {(strategy?.symbols ?? schema?.symbols ?? ["BTC"]).map((sym) => (
                <label key={sym} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={symbols.includes(sym)}
                    onChange={(e) => {
                      setSymbols((prev) =>
                        e.target.checked
                          ? [...prev, sym]
                          : prev.filter((s) => s !== sym),
                      );
                    }}
                  />
                  {sym}
                </label>
              ))}
            </div>
            {fieldErrors.symbols && (
              <span className="text-xs text-red-300">{fieldErrors.symbols}</span>
            )}
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-text-muted">Startdatum</span>
              <input
                type="date"
                className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Enddatum</span>
              <input
                type="date"
                className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </label>
          </div>
          {fieldErrors.time_range && (
            <span className="text-xs text-red-300">{fieldErrors.time_range}</span>
          )}

          <label className="block text-sm">
            <span className="text-text-muted">Timeframe</span>
            <select
              className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
            >
              {(schema?.timeframes ?? ["1D", "1W", "1M"]).map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-xs text-text-muted">
              {strategy?.timeframe_note}
            </span>
          </label>

          <label className="block text-sm">
            <span className="text-text-muted">Startkapital</span>
            <input
              className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5 font-mono"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
            />
            {fieldErrors.starting_capital && (
              <span className="text-xs text-red-300">
                {fieldErrors.starting_capital}
              </span>
            )}
          </label>

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm">
              <span className="text-text-muted">Entry Fee Rate</span>
              <input
                className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5 font-mono"
                value={entryFee}
                onChange={(e) => setEntryFee(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Exit Fee Rate</span>
              <input
                className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5 font-mono"
                value={exitFee}
                onChange={(e) => setExitFee(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Slippage (bps)</span>
              <input
                className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5 font-mono"
                value={slippageBps}
                onChange={(e) => setSlippageBps(e.target.value)}
              />
            </label>
          </div>

          <label className="block text-sm">
            <span className="text-text-muted">Random Seed</span>
            <input
              className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5 font-mono"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </label>

          <div>
            <p className="mb-2 text-sm text-text-muted">Strategieparameter</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {paramKeys.map((key) => (
                <label key={key} className="block text-sm">
                  <span className="font-mono text-xs text-text-muted">{key}</span>
                  <input
                    className="mt-1 w-full rounded border border-border bg-bg-elevated px-2 py-1.5 font-mono"
                    value={parameters[key] ?? ""}
                    onChange={(e) =>
                      setParameters((prev) => ({ ...prev, [key]: e.target.value }))
                    }
                  />
                  {fieldErrors[`parameters.${key}`] && (
                    <span className="text-xs text-red-300">
                      {fieldErrors[`parameters.${key}`]}
                    </span>
                  )}
                </label>
              ))}
            </div>
          </div>

          <button
            type="button"
            className="rounded bg-mint/20 px-3 py-2 text-sm font-medium text-mint hover:bg-mint/30"
            onClick={goSummary}
            data-testid="lab-review"
          >
            Zusammenfassung anzeigen
          </button>
        </Card>
      ) : (
        <Card padding="sm" className="space-y-3" data-testid="research-lab-summary">
          <h2 className="text-sm font-medium">Zusammenfassung</h2>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-text-muted">Strategie</dt>
              <dd className="font-mono">
                {strategyId} @ {strategy?.strategy_version}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted">Name</dt>
              <dd>{name}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Dataset</dt>
              <dd>{datasetId}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Symbole</dt>
              <dd>{symbols.join(", ")}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Zeitraum</dt>
              <dd className="font-mono text-xs">
                {startDate} → {endDate}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted">Kapital</dt>
              <dd className="font-mono">{capital}</dd>
            </div>
          </dl>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded border border-border px-3 py-2 text-sm"
              onClick={() => setStep("form")}
              disabled={submitting}
            >
              Zurück
            </button>
            <button
              type="button"
              className="rounded bg-mint/20 px-3 py-2 text-sm font-medium text-mint hover:bg-mint/30 disabled:opacity-50"
              onClick={() => void createAndStart()}
              disabled={submitting}
              data-testid="lab-start"
            >
              {submitting
                ? "Wird gestartet…"
                : "Experiment erstellen und starten"}
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}
