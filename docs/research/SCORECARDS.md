# Scorecards (Issue #291 / P4.9 Layer 5)

Assembles pinned layer artifacts into a **global evidence profile** and persists
an append-only scorecard record. No second experiment/gate registry. No
re-backtest. No auto-promotion.

Detail drilldowns for the dashboard: Issue
[#350](https://github.com/Pain1234/save-money-trading-bot/issues/350).

Contract: [`REGIME_SCORECARD.md`](REGIME_SCORECARD.md) § Layer 5 / §8.
Related: [`GATES.md`](GATES.md), [`CONFIDENCE.md`](CONFIDENCE.md),
[`VALIDATION_STUDIES.md`](VALIDATION_STUDIES.md).

## Persistenz

Append-only JSONL (mirrors gates):

```text
artifacts/research/scorecards/registry.jsonl
artifacts/research/scorecards/invalidations/<scorecard_id>.jsonl
```

Scorecards are **not** written into the immutable run directory (run dirs already
hold layer sidecars). Invalidation supersedes; originals are never rewritten.

## Deterministic `scorecard_id`

`sc_{sha256}` over:

- `run_id`, optional `gate_run_id`, sorted `robustness_run_ids`
- sealed `robustness_manifest_hashes` (id → #247 manifest content hash)
- scorecard `policy_version` + `policy_content_hash`
- `dataset_id` + `dataset_content_hash`
- `layer_refs` (classification/quality/behaviour/confidence/parameter_area pins)

Re-evaluating the same **active** evidence under the same policy is idempotent.
If the same `scorecard_id` was **invalidated**, evaluate fails closed (no silent
reactivation without new evidence / policy).

## Evidence seal

Each record persists `evidence_content_hash` over immutable fields (profile,
layer refs, limitations, commits, promotion flags, checksums, … — not status /
`evaluated_at`). Reads and ValidationStudy pins recompute and compare; tampering
the JSONL record fails closed.

Optional `robustness_run_ids` are verified via the same #247 path as gates
(completed job, `base_run_id`, sealed manifest hash) and stored under
`artifact_checksums["robustness/{id}/manifest.json"]`. Optional gates also run
`verify_policy_content_hash`.

## Required / optional layers (policy 1.0)

| Layer file | Role |
|------------|------|
| `regime_labels.json` | required |
| `regime_metrics.json` | required |
| `behavior_profile.json` | required |
| `confidence_profile.json` | optional — if missing, derived at evaluate time (not written back) |
| `parameter_area.json` | optional — if missing → `NOT_AVAILABLE`; if present must pass full sealed bind (`evidence_trusted`, completed #247 job + `base_run_id`, policy hash, `evaluate_parameter_area_from_robustness` recompute of `parameter_area_id` / classification). Manifest seal is persisted under `artifact_checksums["robustness/{id}/manifest.json"]` and re-checked on verify |

## API

| Route | Notes |
|-------|-------|
| `GET /api/v1/research/scorecard-policies` | versions + content hash |
| `GET /api/v1/research/scorecards?run_id=` | latest-per-id |
| `GET /api/v1/research/scorecards/{scorecard_id}` | coarse #291 summary; fail-closed integrity for active |
| `GET /api/v1/research/scorecards/{scorecard_id}/detail` | per-regime rows + forensics (#350); summary route unchanged |
| `POST /api/v1/research/scorecards/evaluate` | idempotent assemble |
| `POST /api/v1/research/scorecards/{id}/invalidate` | append-only |

`promotion_action` / `auto_promotion` / `decision_binding` are always false/`none`.

## Detail payload (#350)

`GET .../scorecards/{scorecard_id}/detail` joins **already-pinned** seals only
(`assemble_scorecard_detail` in `services/research/scorecard_detail.py`). It does
not recompute backtests or invent metrics.

| Block | Contents |
|-------|----------|
| `regime_rows[]` | Per `regime_metrics.regimes[]` cell: quality, confidence (scorecard-overall scope), behaviour join, trades, net_pnl, max_drawdown, costs, benchmark_delta |
| `transition_risk` | From sealed `behavior_profile.transition_risk` (else `NOT_AVAILABLE`) |
| `classifier_transitions` | Sealed `regime_labels.json` transitions + period_labels + calendar_gaps + day_events (IDs / period borders / `as_of` time refs) |
| `cost_stress` | `OK` only with sealed base + `combined_elevated` `net_pnl` boundary; else `NOT_AVAILABLE` (no null-verdict OK) |
| `evidence_inputs` | Bound run/gate/robustness/policy/dataset pins + `gate_evidence_content_hash` + promotion flags |
| `gate_failures` | Non-PASS gates **after** verifying scorecard-pinned `gate_evidence_content_hash`; tamper/invalidation → fail-closed (409), not empty list |
| `raw_artifact_refs` | Layer file names + checksum keys + robustness/scorecard refs |
| `missing_data_semantics` | Token `NOT_AVAILABLE` — clients must not coerce to `0` / PASS |

Metric cells use `{ "status": "OK"|"NOT_AVAILABLE", "value": ... }`.
`confidence.scope` is `"scorecard_overall"` when only the scorecard overall label
exists (no per-regime confidence artifact).

### TypeScript-facing sketch (Bot 3 handoff)

```ts
type NaMetric<T> = { status: "OK"; value: T } | { status: "NOT_AVAILABLE"; value: null };

type ScorecardDetail = {
  scorecard_id: string;
  status: "active" | "invalidated";
  decision_binding: false;
  auto_promotion: false;
  promotion_action: "none";
  summary: Record<string, unknown>; // #291 record shape
  regime_rows: Array<{
    cell_id: string;
    trend: string | null;
    vol: string | null;
    quality: NaMetric<string> & { reason?: string };
    confidence: { status: string; value: string | null; scope: "scorecard_overall" };
    behaviour: {
      status: string;
      main_weakness: string;
      main_strength: string;
      labels: string[];
    };
    trades: NaMetric<number>;
    net_pnl: NaMetric<string>;
    max_drawdown: NaMetric<string>;
    costs: NaMetric<{ fees: string; slippage_costs: string; funding_costs: string }>;
    benchmark_delta: NaMetric<string>;
    row_status?: string;
  }>;
  transition_risk: NaMetric<unknown> | { status: "OK"; value: unknown };
  classifier_transitions:
    | { status: "NOT_AVAILABLE"; value: null; reason: string }
    | {
        status: "OK";
        classification_id?: string;
        transitions: Array<{
          transition_id?: string;
          from_period_id?: string;
          to_period_id?: string;
          from_trend?: string;
          to_trend?: string;
          from_vol?: string;
          to_vol?: string;
        }>;
        period_labels: unknown[];
        calendar_gaps: unknown[];
        day_events: Array<{
          as_of?: string;
          period_id?: string;
          event?: string;
          transition_id?: string | null;
        }>;
      };
  cost_stress:
    | { status: "NOT_AVAILABLE"; value: null; reason: string; robustness_run_id?: string }
    | {
        status: "OK";
        robustness_run_id: string;
        manifest_content_hash: string;
        artifact_path: string;
        boundary: {
          base_net_pnl: string;
          combined_elevated_net_pnl: string;
          base_child_id?: string;
          combined_elevated_child_id?: string;
        };
      };
  evidence_inputs: Record<string, unknown>; // includes gate_evidence_content_hash when bound
  gate_failures: Array<Record<string, unknown>>; // fail-closed on gate tamper / invalidation
  raw_artifact_refs: Array<Record<string, unknown>>;
  missing_data_semantics: { token: "NOT_AVAILABLE"; rule: string };
  evidence_integrity: { ok: boolean; error: string | null };
};
```

Tests: `tests/research/test_scorecard_detail.py`.

## Validation Study pin (#249 extension)

Studies (schema `1.2`) accept optional `scorecard_ids`. Each active scorecard is
pinned by `scorecard_evidence_content_hash` into `evidence_snapshot.scorecards`.
Decided studies re-verify pins fail-closed.

## Policy hash

`SCORECARD_POLICY_1_0_CONTENT_HASH` in `scorecard_policy.py` (literal regression pin).

## Acceptance matrix (#293)

`tests/research/test_scorecard_e2e_acceptance.py` covers reproducibility and
anti-overfit boundaries against public synthetic fixtures only:

```text
python -m pytest tests/research/test_scorecard_e2e_acceptance.py -q
```

- identical inputs → identical `scorecard_id`
- JSONL / run-artifact tamper fail-closed
- gate FAIL remains FAIL (not healed by quality layers)
- invalidation blocks reactivation
- policy version unknown + silent content mutation under same version
- insufficient sample cannot yield HIGH confidence
- untrusted `parameter_area.json` fail-closed; trusted sealed PA pins into scorecard
- `integrity_status=INVALID` blocks `quality_scores_permitted`
- Sideways zero-trades → `DEFENSIVE_INACTIVE`; Bull whipsaw weakness
- no auto-promotion / decision_binding
- Research API evaluate smoke **without** `RESEARCH_ALLOW_DIRTY_GIT` (clean temp git)

**UI E2E** for scorecard surfaces is deferred to
[#292](https://github.com/Pain1234/save-money-trading-bot/issues/292) /
[#250](https://github.com/Pain1234/save-money-trading-bot/issues/250)
(issue #293 AC “Research API und UI E2E” is satisfied for API only until UI lands).
