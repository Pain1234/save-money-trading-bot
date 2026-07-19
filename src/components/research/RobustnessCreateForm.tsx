"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { rs } from "@/components/research/chrome/ResearchPageChrome";
import { Card } from "@/components/ui/Card";
import type { RobustnessTestType } from "@/lib/research-api/client";

export interface CompletedExperimentOption {
  experiment_id: string;
  strategy_version: string;
  created_at: string;
}

export interface RobustnessDatasetOption {
  id: string;
  label: string;
}

interface RobustnessCreateFormProps {
  experiments: CompletedExperimentOption[];
  datasets: RobustnessDatasetOption[];
}

const TEST_TYPE_LABELS: Record<RobustnessTestType, string> = {
  walk_forward: "Walk-Forward",
  cost_stress: "Cost Stress",
  parameter_stability: "Parameter Stability",
  bootstrap: "Bootstrap / Monte Carlo",
};

const TEST_TYPE_DESCRIPTIONS: Record<RobustnessTestType, string> = {
  walk_forward:
    "Chronologische Folds mit Feature-Warmup und Embargo (P5-04); dieselben eingefrorenen Parameter je Fold.",
  cost_stress:
    "Vordefinierte Fee-/Slippage-/Funding-Szenarien auf Basis der Spec-Kosten (P5-05).",
  parameter_stability:
    "Ein-Parameter-Nachbarschaft um die eingefrorenen Werte (P5-06, nur diagnostisch).",
  bootstrap:
    "Block-Bootstrap über die Netto-PnL-Reihe eines abgeschlossenen Laufs (P5-07); kein neuer Engine-Lauf.",
};

export function RobustnessCreateForm({
  experiments,
  datasets,
}: RobustnessCreateFormProps) {
  const router = useRouter();
  const [baseExperimentId, setBaseExperimentId] = useState(
    experiments[0]?.experiment_id ?? "",
  );
  const [testType, setTestType] = useState<RobustnessTestType>("walk_forward");
  const [datasetCatalogId, setDatasetCatalogId] = useState(datasets[0]?.id ?? "");
  const [nFolds, setNFolds] = useState("4");
  const [embargoDays, setEmbargoDays] = useState("90");
  const [blockLength, setBlockLength] = useState("5");
  const [nSimulations, setNSimulations] = useState("1000");
  const [seed, setSeed] = useState("42");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const needsDataset = testType !== "bootstrap";

  const config = useMemo(() => {
    if (testType === "walk_forward") {
      return { n_folds: Number(nFolds), embargo_days: Number(embargoDays) };
    }
    if (testType === "bootstrap") {
      return {
        block_length: Number(blockLength),
        n_simulations: Number(nSimulations),
        seed: Number(seed),
      };
    }
    return {};
  }, [testType, nFolds, embargoDays, blockLength, nSimulations, seed]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setFieldErrors({});
    if (!baseExperimentId) {
      setFieldErrors({ base_experiment_id: "Basis-Experiment ist erforderlich" });
      return;
    }
    if (needsDataset && !datasetCatalogId) {
      setFieldErrors({ dataset_catalog_id: "Dataset ist erforderlich" });
      return;
    }
    setSubmitting(true);
    try {
      const createResp = await fetch("/api/research/robustness", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_experiment_id: baseExperimentId,
          test_type: testType,
          ...(needsDataset ? { dataset_catalog_id: datasetCatalogId } : {}),
          config,
        }),
      });
      const createBody = await createResp.json();
      if (!createResp.ok) {
        setFieldErrors(createBody?.detail?.fields ?? {});
        setFormError(createBody?.detail?.message ?? "Erstellen fehlgeschlagen");
        return;
      }
      const robustnessId = createBody.robustness_id as string;
      if (createBody.status === "created") {
        const startResp = await fetch(
          `/api/research/robustness/${encodeURIComponent(robustnessId)}/start`,
          { method: "POST" },
        );
        if (!startResp.ok) {
          const startBody = await startResp.json();
          setFormError(startBody?.detail?.message ?? "Start fehlgeschlagen");
        }
      }
      router.push(
        `/dashboard/research/robustness/${encodeURIComponent(robustnessId)}`,
      );
    } catch {
      setFormError("Netzwerkfehler beim Erstellen/Starten");
    } finally {
      setSubmitting(false);
    }
  }

  if (experiments.length === 0) {
    return (
      <Card padding="sm" data-testid="robustness-create-empty">
        <p className={rs.muted}>
          Es gibt noch kein abgeschlossenes Experiment. Robustheitstests
          benötigen einen abgeschlossenen Basis-Lauf.
        </p>
      </Card>
    );
  }

  return (
    <Card padding="sm" data-testid="robustness-create-form">
      <h2 className={rs.sectionTitle}>Neuer Robustheitstest</h2>
      <form onSubmit={onSubmit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-[12px]">
            <span className={`mb-1 block ${rs.label}`}>Basis-Experiment</span>
            <select
              value={baseExperimentId}
              onChange={(e) => setBaseExperimentId(e.target.value)}
              className={`w-full font-mono ${rs.select}`}
              data-testid="robustness-base-experiment-select"
            >
              {experiments.map((exp) => (
                <option key={exp.experiment_id} value={exp.experiment_id}>
                  {exp.experiment_id} ({exp.strategy_version})
                </option>
              ))}
            </select>
            {fieldErrors.base_experiment_id && (
              <p className="mt-1 text-[11px] text-red-300">
                {fieldErrors.base_experiment_id}
              </p>
            )}
          </label>

          <label className="text-[12px]">
            <span className={`mb-1 block ${rs.label}`}>Testart</span>
            <select
              value={testType}
              onChange={(e) => setTestType(e.target.value as RobustnessTestType)}
              className={`w-full ${rs.select}`}
              data-testid="robustness-test-type-select"
            >
              {(Object.keys(TEST_TYPE_LABELS) as RobustnessTestType[]).map((key) => (
                <option key={key} value={key}>
                  {TEST_TYPE_LABELS[key]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <p className="text-[11px] text-text-secondary">
          {TEST_TYPE_DESCRIPTIONS[testType]}
        </p>

        {needsDataset && (
          <label className="block text-[12px]">
            <span className={`mb-1 block ${rs.label}`}>Dataset</span>
            <select
              value={datasetCatalogId}
              onChange={(e) => setDatasetCatalogId(e.target.value)}
              className={`w-full ${rs.select}`}
              data-testid="robustness-dataset-select"
            >
              {datasets.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.label}
                </option>
              ))}
            </select>
            {fieldErrors.dataset_catalog_id && (
              <p className="mt-1 text-[11px] text-red-300">
                {fieldErrors.dataset_catalog_id}
              </p>
            )}
          </label>
        )}

        {testType === "walk_forward" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-[12px]">
              <span className={`mb-1 block ${rs.label}`}>Anzahl Folds</span>
              <input
                type="number"
                min={1}
                value={nFolds}
                onChange={(e) => setNFolds(e.target.value)}
                className={`w-full ${rs.input}`}
              />
            </label>
            <label className="text-[12px]">
              <span className={`mb-1 block ${rs.label}`}>Embargo (Tage)</span>
              <input
                type="number"
                min={0}
                value={embargoDays}
                onChange={(e) => setEmbargoDays(e.target.value)}
                className={`w-full ${rs.input}`}
              />
            </label>
          </div>
        )}

        {testType === "bootstrap" && (
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-[12px]">
              <span className={`mb-1 block ${rs.label}`}>Blocklänge</span>
              <input
                type="number"
                min={1}
                value={blockLength}
                onChange={(e) => setBlockLength(e.target.value)}
                className={`w-full ${rs.input}`}
              />
            </label>
            <label className="text-[12px]">
              <span className={`mb-1 block ${rs.label}`}>Simulationen</span>
              <input
                type="number"
                min={1}
                value={nSimulations}
                onChange={(e) => setNSimulations(e.target.value)}
                className={`w-full ${rs.input}`}
              />
            </label>
            <label className="text-[12px]">
              <span className={`mb-1 block ${rs.label}`}>Seed</span>
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                className={`w-full ${rs.input}`}
              />
            </label>
          </div>
        )}

        {formError && (
          <p className="text-[12px] text-red-300" data-testid="robustness-form-error">
            {formError}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className={`${rs.btnPrimary} disabled:opacity-50`}
          data-testid="robustness-submit"
        >
          {submitting ? "Wird erstellt…" : "Test erstellen und starten"}
        </button>
      </form>
    </Card>
  );
}
