import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { RobustnessCreateForm } from "../../src/components/research/RobustnessCreateForm";
import { RobustnessJobPanel } from "../../src/components/research/RobustnessJobPanel";
import { RobustnessManifestView } from "../../src/components/research/RobustnessManifestView";
import { RobustnessTable } from "../../src/components/research/RobustnessTable";
import type {
  RobustnessJobDetail,
  RobustnessJobSummary,
  RobustnessManifest,
} from "../../src/lib/research-api/client";

// Synthetic/public fixtures only — no private Strategy V1 numbers (Issue #247).
const SYNTHETIC_JOB: RobustnessJobSummary = {
  robustness_id: "rob_synthetic0000000000000000000000000000000000000000000000000000",
  base_experiment_id: "exp_synthetic_base",
  test_type: "walk_forward",
  status: "completed",
  created_at: "2024-01-01T00:00:00.000000Z",
  updated_at: "2024-01-01T00:05:00.000000Z",
  started_at: "2024-01-01T00:00:05.000000Z",
  finished_at: "2024-01-01T00:05:00.000000Z",
  error: null,
  error_detail: null,
  dataset_catalog_id: "local-btc-fixture",
  config: { n_folds: 2, embargo_days: 0 },
};

const SYNTHETIC_MANIFEST: RobustnessManifest = {
  schema_version: "1.0",
  robustness_id: SYNTHETIC_JOB.robustness_id,
  test_type: "walk_forward",
  base_experiment_id: "exp_synthetic_base",
  base_run_id: "run_synthetic_base",
  dataset_catalog_id: "local-btc-fixture",
  config: { n_folds: 2, embargo_days: 0 },
  created_at: "2024-01-01T00:05:00.000000Z",
  children: [
    {
      child_id: "fold_01",
      label: "fold_01",
      experiment_id: "exp_fold_01",
      run_id: "run_fold_01",
      status: "complete",
      net_pnl: "123.45",
      max_drawdown: "-45.00",
      closed_trades: 3,
      profit_factor: "1.5",
      error: null,
    },
    {
      child_id: "fold_02",
      label: "fold_02",
      experiment_id: null,
      run_id: null,
      status: "failed",
      net_pnl: null,
      max_drawdown: null,
      closed_trades: null,
      profit_factor: null,
      error: "no daily candles remain after applying time_range",
    },
  ],
  bootstrap_result: null,
  summary: { n_children: 2, n_complete: 1, n_failed: 1 },
};

describe("RobustnessTable (static render, synthetic fixtures)", () => {
  it("renders empty state without any jobs", () => {
    const html = renderToStaticMarkup(<RobustnessTable items={[]} />);
    expect(html).toContain("robustness-list-empty");
  });

  it("renders a job row linking to its detail page and base experiment", () => {
    const html = renderToStaticMarkup(<RobustnessTable items={[SYNTHETIC_JOB]} />);
    expect(html).toContain("robustness-list-ready");
    expect(html).toContain("Walk-Forward");
    expect(html).toContain(
      `href="/dashboard/research/robustness/${SYNTHETIC_JOB.robustness_id}"`,
    );
    expect(html).toContain(
      `href="/dashboard/research/experiments/${SYNTHETIC_JOB.base_experiment_id}"`,
    );
    expect(html).toContain("completed");
  });
});

describe("RobustnessManifestView (static render, synthetic fixtures)", () => {
  it("renders pending state before a manifest artifact exists", () => {
    const html = renderToStaticMarkup(<RobustnessManifestView manifest={null} />);
    expect(html).toContain("robustness-manifest-pending");
  });

  it("renders per-child results including a failed neighbor/fold", () => {
    const html = renderToStaticMarkup(
      <RobustnessManifestView manifest={SYNTHETIC_MANIFEST} />,
    );
    expect(html).toContain("robustness-manifest-ready");
    expect(html).toContain("robustness-child-fold_01");
    expect(html).toContain("robustness-child-fold_02");
    expect(html).toContain("123.45");
    expect(html).toContain("no daily candles remain after applying time_range");
    // Summary must surface partial failure, not hide it.
    expect(html).toMatch(/n_failed|Fehlgeschlagen/);
  });

  it("renders bootstrap quantiles when present", () => {
    const manifestWithBootstrap: RobustnessManifest = {
      ...SYNTHETIC_MANIFEST,
      test_type: "bootstrap",
      bootstrap_result: {
        n_simulations: 1000,
        block_length: 5,
        seed: 42,
        net_pnl_quantiles: { q05: -10, q50: 5, q95: 20 },
        max_drawdown_quantiles: { q05: -30, q50: -10, q95: -1 },
        mean_net_pnl: 5,
        mean_max_drawdown: -12,
      },
    };
    const html = renderToStaticMarkup(
      <RobustnessManifestView manifest={manifestWithBootstrap} />,
    );
    expect(html).toContain("robustness-bootstrap-result");
    expect(html).toContain("q05");
  });
});

describe("RobustnessJobPanel (static render, synthetic fixtures)", () => {
  it("renders completed status without an error panel", () => {
    const detail: RobustnessJobDetail = {
      robustness_id: SYNTHETIC_JOB.robustness_id,
      status: "completed",
      test_type: "walk_forward",
      base_experiment_id: "exp_synthetic_base",
      started_at: SYNTHETIC_JOB.started_at,
      finished_at: SYNTHETIC_JOB.finished_at,
      elapsed_seconds: 295,
      error: null,
      error_detail: null,
      job: SYNTHETIC_JOB,
      worker_alive: false,
      manifest: SYNTHETIC_MANIFEST,
    };
    const html = renderToStaticMarkup(
      <RobustnessJobPanel robustnessId={detail.robustness_id} initial={detail} />,
    );
    expect(html).toContain("robustness-job-panel");
    expect(html).toContain("completed");
    expect(html).not.toContain("robustness-job-error");
  });

  it("surfaces partial-failure error text for a completed suite", () => {
    const detail: RobustnessJobDetail = {
      robustness_id: SYNTHETIC_JOB.robustness_id,
      status: "completed",
      test_type: "walk_forward",
      base_experiment_id: "exp_synthetic_base",
      started_at: SYNTHETIC_JOB.started_at,
      finished_at: SYNTHETIC_JOB.finished_at,
      elapsed_seconds: 295,
      error: "1 von 2 Kind-Läufen fehlgeschlagen",
      error_detail: "[]",
      job: SYNTHETIC_JOB,
      worker_alive: false,
      manifest: SYNTHETIC_MANIFEST,
    };
    const html = renderToStaticMarkup(
      <RobustnessJobPanel robustnessId={detail.robustness_id} initial={detail} />,
    );
    expect(html).toContain("robustness-job-error");
    expect(html).toContain("Kind-Läufen fehlgeschlagen");
  });
});

describe("RobustnessCreateForm (static render, synthetic fixtures)", () => {
  it("renders empty state without a completed base experiment", () => {
    const html = renderToStaticMarkup(
      <RobustnessCreateForm experiments={[]} datasets={[]} />,
    );
    expect(html).toContain("robustness-create-empty");
  });

  it("renders the form with base-experiment and test-type selectors", () => {
    const html = renderToStaticMarkup(
      <RobustnessCreateForm
        experiments={[
          {
            experiment_id: "exp_synthetic_base",
            strategy_version: "1.0.0",
            created_at: "2024-01-01T00:00:00.000000Z",
          },
        ]}
        datasets={[{ id: "local-btc-fixture", label: "Local BTC fixture (dev)" }]}
      />,
    );
    expect(html).toContain("robustness-create-form");
    expect(html).toContain("robustness-base-experiment-select");
    expect(html).toContain("robustness-test-type-select");
    expect(html).toContain("exp_synthetic_base");
    expect(html).toContain("robustness-submit");
  });
});
