# P5 Gate 1 Handoff (Agent 1 → Agents 2/3)

**Status:** PREPARED — binding after human `FREEZE PIN REFRESHED` on #196
**Public-core merge:** [#363](https://github.com/Pain1234/save-money-trading-bot/issues/363) via [PR #366](https://github.com/Pain1234/save-money-trading-bot/pull/366)
**Holdout:** `SEALED` (`NO` — do not open)

Agents 2 and 3 must not produce final Partition B evidence until this package is
acknowledged and the private executor is pinned to `public_core_sha`.

```yaml
public_core_sha: "aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4"
experiment_spec_schema_version: "1.0"
runner_version: "aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4"
symbol_constraints_hash: "e5b2254249179eebe89d8d349b2a44566b50fbe79b37b2f32b62dc8d3b364817"
constraint_set_version: "hl-mainnet-szdecimals-v1"
strategy_id: "trend_v1"
strategy_version: "1.0.0"
candidate_freeze_hash: "90214c9031ccc91091a24a171991fbf84032c45845154cd78b4350ed0bfb59d6"
holdout_status: "SEALED"
```

## Binding rules

- Pin private research executor / `PINNED_PUBLIC_CORE.txt` to `public_core_sha`.
- Require Spec `symbol_constraints` matching `symbol_constraints_hash`.
- Do not use pre-#363 private packs as evidence (#251–#254).
- Do not change Strategy V1 parameters or decision thresholds after seeing results.
- Do not open holdout / #204.
- One issue per branch/PR: Agent 2 `#251` then `#252`; Agent 3 `#253` then `#254`.
- Public repo: status + SHA + artifact refs only — no private metrics.

## Evidence recorded on public core

```text
PYTHONPATH=services python -m pytest tests/research \
  tests/paper_trading/test_backtester_signal_parity.py \
  tests/paper_trading/test_backtester_parity.py \
  tests/research/test_double_run_repro.py \
  tests/research/test_symbol_constraints_seal.py \
  -q -m "not postgres and not live and not soak and not reporting"
# 498 passed, 1 skipped @ aa0e232
```

See also: `P5_CANDIDATE_FREEZE.md`, `P5_EXECUTION_STATUS.md`.
