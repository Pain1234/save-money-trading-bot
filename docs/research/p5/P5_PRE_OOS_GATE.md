# P5 Pre-OOS Gate Checklist (#204 blocker)

**Status:** DOCS MERGED — still blocked on human approval + calendar sufficiency
**Holdout opened?** `NO` / `SEALED`
**Do not run #204** until every required box below is checked **and** a human
comments `PRE-OOS APPROVED` on [#204](https://github.com/Pain1234/save-money-trading-bot/issues/204)
with the public-core SHA + UTC.

Phase-3 / Pre-OOS docs are on `main` via PR #369 (`c469b65…`). That merge alone
does **not** open the holdout.

This checklist is process-only. It does **not** contain private economic metrics
and does **not** decide `ACCEPT_FOR_P6` / `REJECT` / `INCONCLUSIVE` (#205).

## Required before #204

| Item | State | Evidence |
|------|-------|----------|
| #363 sealed symbol constraints | **Done** | PR #366 @ `aa0e232…` |
| #196 freeze pin refreshed | **Done** | `FREEZE PIN REFRESHED` 2026-07-19T15:47:02Z |
| #197 partitions locked | **Done** | `PARTITIONS LOCKED` |
| #198 protocol + decision rules frozen | **Done** | `PROTOCOL FROZEN` / `DECISION RULES FROZEN` |
| #199 benchmarks / regimes approved | **Done** | `BENCHMARKS AND REGIMES APPROVED` |
| #294 scorecard/policy bind | **Done** | `SCORECARD POLICY BIND FROZEN` |
| #251 Walk-Forward complete + reviewed | **Done** | private PR #2; Phase-3 cross-check |
| #252 Cost/Funding stress complete + reviewed | **Done** | private PR #3; Phase-3 cross-check |
| #253 Parameter stability complete + reviewed | **Done** | private PR #4; Phase-3 cross-check |
| #254 Bootstrap/MC complete + reviewed | **Done** | private PR #5; Phase-3 cross-check |
| No open technical invalidations | **Clear** | Phase-3: 130/0 integrity checks |
| No unexplained config mutation | **Clear** | shared base + pins across packs |
| Private artifacts sealed | **Done** | private repo `main` after PR #5 |
| Holdout still unopened | **SEALED** | `P5_EXECUTION_STATUS.md` / private status |
| Human Pre-OOS approval | **REQUIRED** | comment on #204 |
| Forward holdout ≥ 90 calendar days | **NOT MET** (2026-07-19 check) | Clock start `2026-07-19T12:54:01Z`; earliest ~`2026-10-17T12:54:01Z` |
| Feature warmup at #204 open | **Confirm at open** | Monthly EMA-20 ⇒ ≥20 completed months in feature context |

## Binding execution pin (for #204 when approved)

```yaml
public_core_sha: "aa0e232a6a0ea235a8a10682f8c7c4229b15a4d4"
symbol_constraints_hash: "e5b2254249179eebe89d8d349b2a44566b50fbe79b37b2f32b62dc8d3b364817"
strategy_id: "trend_v1"
strategy_version: "1.0.0"
candidate_freeze_hash: "90214c9031ccc91091a24a171991fbf84032c45845154cd78b4350ed0bfb59d6"
holdout_status: "SEALED"   # flips only at approved #204 start
```

## Still human / process (not Agent-decided)

- Forward holdout length ≥ 90 calendar days (frozen protocol) — **calendar-blocked
  until ~2026-10-17** unless a dedicated human protocol change issue amends the rule.
- Feature warmup for the evaluation engine — confirm at #204 open.
- Human `PRE-OOS APPROVED` on #204 with SHA + UTC (may be recorded before the
  calendar gate clears; Agents still must not open holdout until both are true).
- Decision Log entry for Pre-OOS approval (process only).
- Exactly one economic OOS run; no threshold/parameter edits after start.
- Repeat only on documented technical fault found **before** economic result review.

## Explicit non-actions

- No Agent may open holdout without human `PRE-OOS APPROVED`.
- No Agent may discuss interim economic OOS results to retune.
- No Agent may auto-promote to P6 (`ACCEPT_FOR_P6` is human #205 only).

## Related docs

- Phase-3 receipt: [`P5_PHASE3_CROSS_CHECK.md`](P5_PHASE3_CROSS_CHECK.md)
- Gate-1 handoff: [`P5_GATE1_HANDOFF.md`](P5_GATE1_HANDOFF.md)
- Execution status: [`P5_EXECUTION_STATUS.md`](P5_EXECUTION_STATUS.md)
