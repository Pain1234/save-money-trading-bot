# Gate evaluator and gate persistence (Issue #248 / P4.7c)

Versioned, evidence-bound evaluation of already-produced research evidence
(#141-#147 runner/registry, #247 robustness orchestrator) against a
versioned gate policy. **No second backtest engine. No auto-promotion into
paper or live trading anywhere in this surface.**

This is generic P4.7c infrastructure for the future Validation Study API
(#249). It does **not** implement the private, human-owned P5 decision
rules (`docs/research/p5/P5_DECISION_RULES.md`, still "GATES PROPOSED") and
must never be treated as a substitute for that human sign-off (#205).

## Evidence-binding contract (mandatory)

A `policy_version` + threshold + measured value alone are **not** enough.
Every persisted `GateRunRecord` carries:

| Field | Source |
|-------|--------|
| `run_id` (+ optional `robustness_run_ids`) | Caller input, verified against the registry / robustness artifacts |
| `artifact_checksums` | Registry trust-anchor checksums for the run + a SHA-256 seal per evaluated robustness `manifest.json` |
| `dataset_id` / `dataset_content_hash` | The run's sealed `RunManifest` (#142) |
| `policy_version` **and** `policy_content_hash` | `research.gate_policy` — content hash, not version string alone |
| `run_code_commit` | The run's sealed `RunManifest.git_commit` |
| `evaluation_code_commit` | Deploy pin `RESEARCH_EVALUATION_GIT_SHA` / `RAILWAY_GIT_COMMIT_SHA` if set; else clean `git rev-parse HEAD` (dirty tree fails closed). Never falls back to the evaluated run's `git_commit`. |

`GateEvaluator.evaluate()` fails closed (`GateEvaluationError`) if the run is
not `complete`, if artifacts were tampered with (registry checksum verify),
if a referenced robustness manifest is missing or its seal
(`job.manifest_content_hash` / `manifest.json.sha256`) does not match, or if
`policy_version` is unknown. Robustness gate measurements are taken from
verified child `metrics.json` / recomputed bootstrap equity — not from
mutable `children[].net_pnl` / `bootstrap_result` copies alone. Robustness
evidence additionally fails closed unless every loaded manifest has a valid
schema/version, matching `robustness_id`, exact `base_run_id` pin to the
evaluated run (no cross-run evidence), matching dataset binding, verified
complete child runs (registry + checksums), and **no duplicate `test_type`**
across the requested ids (silent overwrite of measured values is rejected).
`GateService.get` / `list_all` re-verify `policy_content_hash` and stored
`artifact_checksums` on read and refuse to present active records as trusted
after a same-version silent policy edit or post-evaluation evidence tamper.

## Policy versioning (content-hash bound)

`research.gate_policy.GatePolicy` is versioned data (`GateDefinition` name /
metric / comparator / threshold), never code branching on private numbers.
The binding identity for a persisted record is the policy's SHA-256 content
hash (`compute_policy_content_hash`), **not** the version string alone:

- Extend by adding a **new** version key to the registry.
- Never mutate an existing version's `gates` tuple in place — that is
  exactly the failure mode `verify_policy_content_hash` exists to catch: if
  version `"1.0"` were silently re-defined with different thresholds, a
  persisted record's old content hash no longer matches the current
  in-repo definition for that version, and re-verification raises
  `GatePolicyError` (`tests/research/test_gate_policy.py`).

## Persistence (append-only, immutable invalidation)

`GateResultStore` mirrors `research.registry.ExperimentRegistry`:

- Records are appended to
  `artifacts/research/gates/registry.jsonl` — never rewritten.
- `gate_run_id` is deterministic (SHA-256 over `run_id` +
  `policy_version` + `policy_content_hash` + `robustness_run_ids`), so
  re-evaluating the same evidence under the same policy content is
  idempotent (returns the existing active record instead of appending a
  duplicate).
- Invalidating a result appends a **superseding** record (`status:
  "invalidated"` + `invalidation_reason`) plus a sidecar under
  `artifacts/research/gates/invalidations/<gate_run_id>.jsonl` — the
  original record line is never edited or deleted.

## No auto-promotion

`GateRunRecord.promotion_action` is always `"none"`. No code path in
`gate_policy.py` / `gate_evaluator.py` / `gate_service.py` calls into
`paper_trading` or any live order surface. `overall_status: "fail" | "pass"`
is informational evidence only — promotion remains a separate, human-owned
decision (#205 for Strategy V1; P6/P8 milestones generally).

## Extension path — Regime Evidence Scorecard (P4.9)

Epic [#295](https://github.com/Pain1234/save-money-trading-bot/issues/295) /
contract [`REGIME_SCORECARD.md`](REGIME_SCORECARD.md) extends this surface with:

- Layer-0 **Integrity** profile (`VALID` / `INVALID` / `NOT_VERIFIABLE`) that
  blocks trusted quality scoring when invalid ([#286](https://github.com/Pain1234/save-money-trading-bot/issues/286))
- Explicit gate outcomes `INCONCLUSIVE` / `NOT_AVAILABLE` (missing evidence must
  never appear as `PASS`)
- Critical-gate **categories** (drawdown, OOS net, walk-forward, cost stress,
  parameter fragility, concentration, bootstrap tail, regime coverage, sample
  sufficiency, execution realism) — still content-hash bound; still no private
  Strategy V1 numbers in the generic P4 policy

Do **not** create a second gate evaluator or gate registry. Regime quality scores
must not compensate a critical gate `FAIL`.

## API

`services/research/api.py` (`/api/v1/research/...`):

| Route | Purpose |
|-------|---------|
| `GET /gate-policies` | Registered policy versions + content hash (read-only, no secrets) |
| `GET /gates` | List gate results (optional `?run_id=`) |
| `GET /gates/{gate_run_id}` | One gate result |
| `POST /gates/evaluate` | Evaluate `{run_id, policy_version, robustness_run_ids?}` (idempotent) |
| `POST /gates/{gate_run_id}/invalidate` | Append-only invalidation `{reason, actor}` |

## Tests

- `tests/research/test_gate_policy.py` — content-hash determinism, unknown
  version, and the same-version-content-hash-mismatch case.
- `tests/research/test_gate_evaluator.py` — evidence binding, tampered
  artifact rejection, robustness-manifest binding, idempotent append-only
  persistence, invalidation.
- `tests/research/test_gate_api.py` — integration (local BTC fixture).
