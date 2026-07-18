"""Safe read access over ExperimentRegistry + run artifacts (Issue #240)."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from research.artifacts import verify_checksums_against
from research.registry import ExperimentRegistry, RegistryEntry
from research.strategy_resolver import catalog_strategy_ids, known_strategy_ids

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UNAVAILABLE = "Nicht verfügbar"


def research_root_from_env() -> Path:
    raw = os.environ.get("RESEARCH_ARTIFACTS_ROOT", ".").strip() or "."
    return Path(raw).resolve()


def assert_safe_id(value: str, *, field: str = "id") -> str:
    if not _SAFE_ID.fullmatch(value):
        msg = f"invalid {field}"
        raise ValueError(msg)
    return value


def resolve_under_root(root: Path, candidate: Path) -> Path:
    """Resolve candidate and ensure it stays under root (path-traversal safe)."""
    root_resolved = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        msg = "path escapes research artifacts root"
        raise PermissionError(msg) from exc
    return resolved


@dataclass(frozen=True)
class ExperimentSummary:
    experiment_id: str
    run_id: str
    status: str
    strategy_version: str
    strategy_id: str | None
    dataset_version: str
    cost_model_version: str
    benchmark_ref: str
    created_at: str
    symbols: list[str]
    time_range_start: str | None
    time_range_end: str | None
    timeframe: str | None
    git_commit: str | None
    duration_seconds: float | None
    net_pnl: str | None
    max_drawdown: str | None
    closed_trades: int | None
    hit_rate: str | None
    profit_factor: str | None
    integrity_ok: bool
    integrity_error: str | None


def _empty_summary(
    entry: RegistryEntry,
    *,
    integrity_ok: bool,
    integrity_error: str | None,
) -> ExperimentSummary:
    return ExperimentSummary(
        experiment_id=entry.experiment_id,
        run_id=entry.run_id,
        status=entry.status,
        strategy_version=entry.strategy_version,
        strategy_id=None,
        dataset_version=entry.dataset_version,
        cost_model_version=entry.cost_model_version,
        benchmark_ref=entry.benchmark_ref,
        created_at=entry.created_at,
        symbols=[],
        time_range_start=None,
        time_range_end=None,
        timeframe=None,
        git_commit=None,
        duration_seconds=None,
        net_pnl=None,
        max_drawdown=None,
        closed_trades=None,
        hit_rate=None,
        profit_factor=None,
        integrity_ok=integrity_ok,
        integrity_error=integrity_error,
    )


class ResearchReadService:
    """Filesystem-backed read API helper. No second registry."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or research_root_from_env()).resolve()
        self.registry = ExperimentRegistry(self.root)
        self.artifacts_root = self.registry.artifacts_root.resolve()

    def _artifact_dir(self, entry: RegistryEntry) -> Path:
        """Resolve the registry trust-path only (no alternate preferred dir)."""
        return resolve_under_root(self.artifacts_root, Path(entry.artifact_path))

    def _verify_complete(self, entry: RegistryEntry, run_dir: Path) -> None:
        """Trust anchor = registry checksum snapshot (same as ExperimentRegistry.show)."""
        if entry.status != "complete":
            return
        if not entry.checksums:
            msg = f"registry entry for {entry.run_id} has empty trusted checksums"
            raise ValueError(msg)
        verify_checksums_against(run_dir, entry.checksums)

    def latest_entries(self) -> list[RegistryEntry]:
        """Last registry line wins per experiment_id (append-only)."""
        latest: dict[str, RegistryEntry] = {}
        for entry in self.registry.list_entries():
            latest[entry.experiment_id] = entry
        return list(latest.values())

    def get_entry(self, experiment_id: str) -> RegistryEntry:
        experiment_id = assert_safe_id(experiment_id, field="experiment_id")
        for entry in reversed(self.registry.list_entries()):
            if entry.experiment_id == experiment_id:
                return entry
        raise KeyError(experiment_id)

    def _load_json(self, run_dir: Path, name: str) -> dict[str, Any] | list[Any] | None:
        path = run_dir / name
        if not path.is_file():
            return None
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(raw, (dict, list)):
            return raw
        return None

    def _enrich(self, entry: RegistryEntry) -> ExperimentSummary:
        try:
            run_dir = self._artifact_dir(entry)
        except (PermissionError, OSError) as exc:
            return _empty_summary(
                entry,
                integrity_ok=False,
                integrity_error=str(exc),
            )

        try:
            self._verify_complete(entry, run_dir)
        except (FileNotFoundError, ValueError, OSError) as exc:
            return _empty_summary(
                entry,
                integrity_ok=False,
                integrity_error=str(exc),
            )

        symbols: list[str] = []
        tr_start: str | None = None
        tr_end: str | None = None
        git_commit: str | None = None
        net_pnl: str | None = None
        max_dd: str | None = None
        closed: int | None = None
        hit_rate: str | None = None
        pf: str | None = None
        strategy_id: str | None = None

        spec = self._load_json(run_dir, "experiment.json")
        if isinstance(spec, dict):
            raw_symbols = spec.get("symbols") or []
            if isinstance(raw_symbols, list):
                symbols = [str(s) for s in raw_symbols]
            tr = spec.get("time_range") or {}
            if isinstance(tr, dict):
                tr_start = str(tr["start"]) if tr.get("start") else None
                tr_end = str(tr["end"]) if tr.get("end") else None
            params = spec.get("parameters") or {}
            if isinstance(params, dict) and params.get("strategy_id") is not None:
                strategy_id = str(params["strategy_id"])

        manifest = self._load_json(run_dir, "run_manifest.json")
        if isinstance(manifest, dict):
            git_commit = str(manifest["git_commit"]) if manifest.get("git_commit") else None

        metrics = self._load_json(run_dir, "metrics.json")
        if isinstance(metrics, dict):
            if metrics.get("net_pnl") is not None:
                net_pnl = str(metrics["net_pnl"])
            if metrics.get("max_drawdown") is not None:
                max_dd = str(metrics["max_drawdown"])
            if metrics.get("closed_trades") is not None:
                try:
                    closed = int(metrics["closed_trades"])
                except (TypeError, ValueError):
                    closed = None
            if metrics.get("hit_rate") is not None:
                hit_rate = str(metrics["hit_rate"])
            if metrics.get("profit_factor") is not None:
                pf = str(metrics["profit_factor"])

        return ExperimentSummary(
            experiment_id=entry.experiment_id,
            run_id=entry.run_id,
            status=entry.status,
            strategy_version=entry.strategy_version,
            strategy_id=strategy_id,
            dataset_version=entry.dataset_version,
            cost_model_version=entry.cost_model_version,
            benchmark_ref=entry.benchmark_ref,
            created_at=entry.created_at,
            symbols=symbols,
            time_range_start=tr_start,
            time_range_end=tr_end,
            timeframe=None,  # Spec has no single timeframe field
            git_commit=git_commit,
            duration_seconds=None,
            net_pnl=net_pnl,
            max_drawdown=max_dd,
            closed_trades=closed,
            hit_rate=hit_rate,
            profit_factor=pf,
            integrity_ok=True,
            integrity_error=None,
        )

    def overview(self) -> dict[str, Any]:
        items = self.list_experiments()
        status_counts: dict[str, int] = {}
        for row in items:
            st = str(row.get("status") or "")
            status_counts[st] = status_counts.get(st, 0) + 1
        recent = items[:10]
        strategies = sorted(
            {
                str(row["strategy_version"])
                for row in items
                if row.get("strategy_version")
            }
        )
        known = sorted(catalog_strategy_ids())
        running = status_counts.get("running", 0) + status_counts.get("queued", 0)
        return {
            "experiment_count": len(items),
            "completed_count": status_counts.get("complete", 0)
            + status_counts.get("completed", 0),
            "failed_count": status_counts.get("failed", 0),
            "invalidated_count": status_counts.get("invalidated", 0),
            "running_count": running,
            "running_available": True,
            "strategy_version_count": len(strategies),
            "known_strategy_ids": known,
            "resolvable_strategy_ids": sorted(known_strategy_ids()),
            "status_distribution": status_counts,
            "recent_experiments": recent,
            "unavailable": {
                "validated_strategies": _UNAVAILABLE,
                "paper_trading_candidates": _UNAVAILABLE,
                "gate_rejection_reasons": _UNAVAILABLE,
                "robustness_scores": _UNAVAILABLE,
                "promotions": _UNAVAILABLE,
            },
        }

    def list_experiments(
        self,
        *,
        status: str | None = None,
        strategy_version: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        items = [self._enrich(e) for e in self.latest_entries()]
        items = self._merge_job_summaries(items)
        if status:
            items = [i for i in items if i.status == status]
        if strategy_version:
            items = [i for i in items if i.strategy_version == strategy_version]
        if q:
            needle = q.strip().lower()
            items = [
                i
                for i in items
                if needle in i.experiment_id.lower()
                or needle in (i.strategy_version or "").lower()
                or needle in i.run_id.lower()
            ]
        items.sort(key=lambda i: i.created_at, reverse=True)
        return [i.__dict__ for i in items]

    def _merge_job_summaries(
        self, items: list[ExperimentSummary]
    ) -> list[ExperimentSummary]:
        from research.jobs import ResearchJobStore

        store = ResearchJobStore(self.root)
        by_id = {i.experiment_id: i for i in items}
        for job in store.list_jobs():
            job = store.mark_stale_if_needed(job)
            if job.experiment_id in by_id:
                base = by_id[job.experiment_id]
                # Prefer live job lifecycle status over registry complete/failed label.
                if job.status in {"created", "queued", "running", "failed", "completed"}:
                    by_id[job.experiment_id] = ExperimentSummary(
                        **{
                            **base.__dict__,
                            "status": (
                                "complete"
                                if job.status == "completed"
                                else job.status
                            ),
                            "run_id": job.run_id or base.run_id,
                            "created_at": job.created_at or base.created_at,
                        }
                    )
            else:
                by_id[job.experiment_id] = ExperimentSummary(
                    experiment_id=job.experiment_id,
                    run_id=job.run_id or "",
                    status=(
                        "complete" if job.status == "completed" else job.status
                    ),
                    strategy_version="",
                    strategy_id=None,
                    dataset_version="",
                    cost_model_version="",
                    benchmark_ref="",
                    created_at=job.created_at,
                    symbols=[],
                    time_range_start=None,
                    time_range_end=None,
                    timeframe=None,
                    git_commit=None,
                    duration_seconds=None,
                    net_pnl=None,
                    max_drawdown=None,
                    closed_trades=None,
                    hit_rate=None,
                    profit_factor=None,
                    integrity_ok=True,
                    integrity_error=None,
                )
        return list(by_id.values())

    def experiment_detail(self, experiment_id: str) -> dict[str, Any]:
        entry = self.get_entry(experiment_id)
        try:
            run_dir = self._artifact_dir(entry)
        except PermissionError as exc:
            raise PermissionError(str(exc)) from exc

        integrity_ok = True
        integrity_error: str | None = None
        try:
            self._verify_complete(entry, run_dir)
        except (FileNotFoundError, ValueError, OSError) as exc:
            integrity_ok = False
            integrity_error = str(exc)

        summary = self._enrich(entry)

        if not integrity_ok:
            return {
                "summary": summary.__dict__,
                "metadata": {
                    "experiment_id": entry.experiment_id,
                    "run_id": entry.run_id,
                    "status": entry.status,
                    "strategy_version": entry.strategy_version,
                    "git_commit": None,
                    "dataset_version": entry.dataset_version,
                    "seed": None,
                    "created_at": entry.created_at,
                    # No durable start timestamp exists on RunManifest today.
                    "started_at": None,
                    "finalized_at": None,
                    "duration_seconds": None,
                },
                "config": {
                    "symbols": [],
                    "time_range_start": None,
                    "time_range_end": None,
                    "timeframe": _UNAVAILABLE,
                    "starting_capital": None,
                    "parameters": {},
                    "fee_assumption": None,
                    "slippage_assumption": None,
                    "funding_assumption": None,
                    "costs": None,
                    "in_sample_config": _UNAVAILABLE,
                    "out_of_sample_config": _UNAVAILABLE,
                    "benchmark": entry.benchmark_ref,
                    "hypothesis": None,
                },
                "metrics": self._metrics_display(None),
                "equity": [],
                "drawdown": [],
                "artifacts": {
                    "has_experiment_spec": False,
                    "has_run_manifest": False,
                    "has_metrics": False,
                    "has_equity": False,
                    "has_costs": False,
                    "has_trades": False,
                    "has_chart_data": False,
                },
                "integrity": {
                    "ok": False,
                    "error": integrity_error or "integrity check failed",
                },
            }

        spec = self._load_json(run_dir, "experiment.json")
        manifest = self._load_json(run_dir, "run_manifest.json")
        costs = self._load_json(run_dir, "costs.json")
        metrics = self._load_json(run_dir, "metrics.json")
        equity = self._load_json(run_dir, "equity.json")

        metrics_display = self._metrics_display(
            metrics if isinstance(metrics, dict) else None
        )
        equity_series, drawdown_series = self._equity_series(
            equity if isinstance(equity, list) else None
        )

        finalized_at: str | None = None
        if isinstance(manifest, dict) and manifest.get("created_at_utc"):
            # Runner writes created_at_utc when finalizing the manifest — not a start time.
            finalized_at = str(manifest["created_at_utc"])

        return {
            "summary": summary.__dict__,
            "metadata": {
                "experiment_id": entry.experiment_id,
                "run_id": entry.run_id,
                "status": entry.status,
                "strategy_version": entry.strategy_version,
                "git_commit": summary.git_commit,
                "dataset_version": entry.dataset_version,
                "seed": (
                    spec.get("random_seed")
                    if isinstance(spec, dict)
                    else None
                ),
                "created_at": entry.created_at,
                "started_at": None,
                "finalized_at": finalized_at,
                "duration_seconds": None,
            },
            "config": {
                "symbols": summary.symbols,
                "time_range_start": summary.time_range_start,
                "time_range_end": summary.time_range_end,
                "timeframe": _UNAVAILABLE,
                "starting_capital": (
                    str(spec["starting_capital"])
                    if isinstance(spec, dict) and spec.get("starting_capital") is not None
                    else None
                ),
                "parameters": (
                    spec.get("parameters") if isinstance(spec, dict) else {}
                ),
                "fee_assumption": (
                    spec.get("fee_assumption") if isinstance(spec, dict) else None
                ),
                "slippage_assumption": (
                    spec.get("slippage_assumption") if isinstance(spec, dict) else None
                ),
                "funding_assumption": (
                    spec.get("funding_assumption") if isinstance(spec, dict) else None
                ),
                "costs": costs if isinstance(costs, dict) else None,
                "in_sample_config": _UNAVAILABLE,
                "out_of_sample_config": _UNAVAILABLE,
                "benchmark": entry.benchmark_ref,
                "hypothesis": (
                    spec.get("hypothesis") if isinstance(spec, dict) else None
                ),
            },
            "metrics": metrics_display,
            "equity": equity_series,
            "drawdown": drawdown_series,
            "artifacts": {
                "has_experiment_spec": isinstance(spec, dict),
                "has_run_manifest": isinstance(manifest, dict),
                "has_metrics": isinstance(metrics, dict),
                "has_equity": isinstance(equity, list),
                "has_costs": isinstance(costs, dict),
                "has_trades": (run_dir / "trades.json").is_file(),
                "has_chart_data": (run_dir / "chart_data.json").is_file(),
            },
            "integrity": {"ok": True, "error": None},
        }

    def _require_verified_complete_run_dir(
        self, experiment_id: str
    ) -> tuple[RegistryEntry, Path]:
        """Only complete registry entries with verified checksums may serve trades/charts."""
        entry = self.get_entry(experiment_id)
        if entry.status != "complete":
            msg = (
                f"experiment {experiment_id!r} status is {entry.status!r}; "
                "trades/chart-data require status 'complete'"
            )
            raise ValueError(msg)
        run_dir = self._artifact_dir(entry)
        # Always verify checksums for complete runs (never skip).
        if not entry.checksums:
            msg = f"registry entry for {entry.run_id} has empty trusted checksums"
            raise ValueError(msg)
        verify_checksums_against(run_dir, entry.checksums)
        return entry, run_dir

    @staticmethod
    def _parse_iso_datetime(raw: object, *, field: str) -> datetime:
        if raw is None or raw == "":
            msg = f"missing {field}"
            raise ValueError(msg)
        text = str(raw).replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(text)
        except ValueError as exc:
            msg = f"invalid {field}: {raw!r}"
            raise ValueError(msg) from exc
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _validate_positive_price(raw: object, *, field: str) -> Decimal:
        if raw is None or raw == "":
            msg = f"missing {field}"
            raise ValueError(msg)
        try:
            value = Decimal(str(raw))
        except Exception as exc:
            msg = f"invalid {field}: {raw!r}"
            raise ValueError(msg) from exc
        if not value.is_finite() or value <= 0:
            msg = f"{field} must be a finite positive price: {raw!r}"
            raise ValueError(msg)
        return value

    @classmethod
    def _validate_candle_ohlcv(cls, row: dict[str, Any], *, index: int) -> None:
        """Fail-closed: no invented zeros; OHLC must be finite, positive, consistent."""
        open_px = cls._validate_positive_price(row.get("open"), field=f"candle[{index}].open")
        high_px = cls._validate_positive_price(row.get("high"), field=f"candle[{index}].high")
        low_px = cls._validate_positive_price(row.get("low"), field=f"candle[{index}].low")
        close_px = cls._validate_positive_price(
            row.get("close"), field=f"candle[{index}].close"
        )
        volume_raw = row.get("volume")
        if volume_raw is None or volume_raw == "":
            volume = Decimal("0")
        else:
            try:
                volume = Decimal(str(volume_raw))
            except Exception as exc:
                msg = f"invalid candle[{index}].volume: {volume_raw!r}"
                raise ValueError(msg) from exc
            if not volume.is_finite() or volume < 0:
                msg = f"candle[{index}].volume must be finite and >= 0"
                raise ValueError(msg)
        if high_px < low_px:
            msg = f"candle[{index}] high < low"
            raise ValueError(msg)
        if high_px < max(open_px, close_px) or low_px > min(open_px, close_px):
            msg = f"candle[{index}] OHLC inconsistent"
            raise ValueError(msg)

    def _spec_time_range_bounds(
        self, spec: dict[str, Any]
    ) -> tuple[datetime, datetime]:
        tr = spec.get("time_range")
        if not isinstance(tr, dict):
            msg = "experiment.json time_range missing"
            raise ValueError(msg)
        start = self._parse_iso_datetime(tr.get("start"), field="time_range.start")
        end = self._parse_iso_datetime(tr.get("end"), field="time_range.end")
        if start > end:
            msg = "experiment.json time_range.start is after time_range.end"
            raise ValueError(msg)
        return start, end

    def _validate_trade_timestamps(
        self,
        trade: dict[str, Any],
        *,
        range_start: datetime,
        range_end: datetime,
        candle_times: set[datetime] | None = None,
    ) -> None:
        """Fail-closed when trade/stop times fall outside the experiment window or candles."""

        def _in_range(ts: datetime, field: str) -> None:
            if ts < range_start or ts > range_end:
                msg = f"{field} {ts.isoformat()} outside experiment time_range"
                raise ValueError(msg)

        def _on_candle_axis(ts: datetime, field: str) -> None:
            if candle_times is None:
                return
            # Allow exact candle open_time or same UTC calendar day as a candle.
            if ts in candle_times:
                return
            days = {t.date() for t in candle_times}
            if ts.date() in days:
                return
            msg = f"{field} {ts.isoformat()} does not match candle time axis"
            raise ValueError(msg)

        entry_time = self._parse_iso_datetime(
            trade.get("entry_time"), field="entry_time"
        )
        _in_range(entry_time, "entry_time")
        _on_candle_axis(entry_time, "entry_time")

        signal_raw = trade.get("signal_time")
        if signal_raw is not None and signal_raw != "":
            signal_time = self._parse_iso_datetime(signal_raw, field="signal_time")
            _in_range(signal_time, "signal_time")

        exit_time: datetime | None = None
        exit_raw = trade.get("exit_time")
        if exit_raw is not None and exit_raw != "":
            exit_time = self._parse_iso_datetime(exit_raw, field="exit_time")
            _in_range(exit_time, "exit_time")
            _on_candle_axis(exit_time, "exit_time")
            if exit_time < entry_time:
                msg = "exit_time is before entry_time"
                raise ValueError(msg)

        prev_stop_time: datetime | None = None
        for idx, snap in enumerate(trade.get("trailing_stop_history") or []):
            if not isinstance(snap, dict):
                msg = f"trailing_stop_history[{idx}] is invalid"
                raise ValueError(msg)
            snap_time = self._parse_iso_datetime(
                snap.get("time"), field=f"trailing_stop_history[{idx}].time"
            )
            _in_range(snap_time, f"trailing_stop_history[{idx}].time")
            _on_candle_axis(snap_time, f"trailing_stop_history[{idx}].time")
            if snap_time < entry_time:
                msg = (
                    f"trailing_stop_history[{idx}].time is before entry_time"
                )
                raise ValueError(msg)
            if exit_time is not None and snap_time > exit_time:
                msg = (
                    f"trailing_stop_history[{idx}].time is after exit_time"
                )
                raise ValueError(msg)
            if prev_stop_time is not None and snap_time < prev_stop_time:
                msg = (
                    f"trailing_stop_history[{idx}].time is out of order"
                )
                raise ValueError(msg)
            self._validate_positive_price(
                snap.get("effective_stop"),
                field=f"trailing_stop_history[{idx}].effective_stop",
            )
            prev_stop_time = snap_time

        initial_stop = trade.get("initial_stop")
        if initial_stop is not None and initial_stop != "":
            self._validate_positive_price(
                initial_stop, field="initial_stop"
            )

    def experiment_trades(
        self,
        experiment_id: str,
        *,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """Return trades.json after complete-run integrity verification (fail-closed)."""
        entry, run_dir = self._require_verified_complete_run_dir(experiment_id)
        spec = self._load_json(run_dir, "experiment.json")
        if not isinstance(spec, dict):
            msg = "experiment.json missing or invalid"
            raise ValueError(msg)
        range_start, range_end = self._spec_time_range_bounds(spec)
        allowed = {
            str(s)
            for s in (spec.get("symbols") or [])
            if s is not None
        }
        if symbol is not None:
            if symbol not in allowed:
                msg = f"symbol {symbol!r} is not part of this experiment"
                raise ValueError(msg)

        trades_raw = self._load_json(run_dir, "trades.json")
        if not isinstance(trades_raw, list):
            msg = "trades.json missing or invalid"
            raise FileNotFoundError(msg)

        trades: list[dict[str, Any]] = []
        for row in trades_raw:
            if not isinstance(row, dict):
                continue
            trade_symbol = str(row.get("symbol") or "")
            if trade_symbol not in allowed:
                msg = (
                    f"trade symbol {trade_symbol!r} not in experiment symbols "
                    f"{sorted(allowed)}"
                )
                raise ValueError(msg)
            if symbol is not None and trade_symbol != symbol:
                continue
            self._validate_trade_timestamps(
                row,
                range_start=range_start,
                range_end=range_end,
            )
            trades.append(row)

        return {
            "experiment_id": entry.experiment_id,
            "run_id": entry.run_id,
            "dataset_version": entry.dataset_version,
            "symbols": sorted(allowed),
            "trades": trades,
            "count": len(trades),
            "integrity": {"ok": True, "error": None},
        }

    def experiment_chart_data(
        self,
        experiment_id: str,
        *,
        symbol: str,
    ) -> dict[str, Any]:
        """Return run-bound candles + trade markers for one symbol."""
        from research.chart_data import CHART_DATA_SCHEMA_VERSION

        entry, run_dir = self._require_verified_complete_run_dir(experiment_id)
        spec = self._load_json(run_dir, "experiment.json")
        if not isinstance(spec, dict):
            msg = "experiment.json missing or invalid"
            raise ValueError(msg)
        range_start, range_end = self._spec_time_range_bounds(spec)
        allowed = {
            str(s)
            for s in (spec.get("symbols") or [])
            if s is not None
        }
        if symbol not in allowed:
            msg = f"symbol {symbol!r} is not part of this experiment"
            raise ValueError(msg)

        chart_raw = self._load_json(run_dir, "chart_data.json")
        if not isinstance(chart_raw, dict):
            msg = (
                "chart_data.json missing — re-run experiment to generate "
                "bound candle artifact"
            )
            raise FileNotFoundError(msg)

        schema_version = str(chart_raw.get("schema_version") or "")
        if schema_version != CHART_DATA_SCHEMA_VERSION:
            msg = (
                f"unsupported chart_data schema_version {schema_version!r}; "
                f"expected {CHART_DATA_SCHEMA_VERSION!r}"
            )
            raise ValueError(msg)

        manifest = self._load_json(run_dir, "run_manifest.json")
        if not isinstance(manifest, dict):
            msg = "run_manifest.json missing or invalid"
            raise ValueError(msg)

        expected_hash = str(manifest.get("dataset_content_hash") or "").strip()
        chart_hash = str(chart_raw.get("dataset_content_hash") or "").strip()
        expected_ds = str(manifest.get("dataset_id") or "").strip()
        chart_ds = str(chart_raw.get("dataset_id") or "").strip()
        if not expected_hash or not chart_hash:
            msg = "dataset_content_hash missing on RunManifest or chart_data"
            raise ValueError(msg)
        if not expected_ds or not chart_ds:
            msg = "dataset_id missing on RunManifest or chart_data"
            raise ValueError(msg)
        if expected_hash != chart_hash:
            msg = "chart_data dataset_content_hash does not match RunManifest"
            raise ValueError(msg)
        if expected_ds != chart_ds:
            msg = "chart_data dataset_id does not match RunManifest"
            raise ValueError(msg)

        symbols_map = chart_raw.get("symbols") or {}
        if not isinstance(symbols_map, dict) or symbol not in symbols_map:
            msg = f"no chart candles for symbol {symbol!r}"
            raise ValueError(msg)
        candles = symbols_map[symbol]
        if not isinstance(candles, list):
            msg = f"invalid candle series for symbol {symbol!r}"
            raise ValueError(msg)

        candle_times: set[datetime] = set()
        for idx, row in enumerate(candles):
            if not isinstance(row, dict):
                msg = f"candle[{idx}] is invalid"
                raise ValueError(msg)
            ts = self._parse_iso_datetime(row.get("time"), field=f"candle[{idx}].time")
            if ts < range_start or ts > range_end:
                msg = f"candle[{idx}].time outside experiment time_range"
                raise ValueError(msg)
            self._validate_candle_ohlcv(row, index=idx)
            candle_times.add(ts)

        # Validate trades against range + candle axis (do not reuse trades endpoint
        # alone — chart must enforce axis alignment).
        trades_payload = self.experiment_trades(experiment_id, symbol=symbol)
        validated_trades: list[dict[str, Any]] = []
        for trade in trades_payload["trades"]:
            self._validate_trade_timestamps(
                trade,
                range_start=range_start,
                range_end=range_end,
                candle_times=candle_times,
            )
            validated_trades.append(trade)

        return {
            "experiment_id": entry.experiment_id,
            "run_id": entry.run_id,
            "symbol": symbol,
            "timeframe": chart_raw.get("timeframe", "1D"),
            "dataset_id": chart_raw.get("dataset_id"),
            "dataset_content_hash": chart_raw.get("dataset_content_hash"),
            "dataset_version": entry.dataset_version,
            "schema_version": schema_version,
            "candles": candles,
            "trades": validated_trades,
            "integrity": {"ok": True, "error": None},
        }

    def _metrics_display(self, metrics: dict[str, Any] | None) -> dict[str, Any]:
        def present(key: str) -> Any:
            if metrics is None or key not in metrics or metrics[key] is None:
                return _UNAVAILABLE
            return str(metrics[key])

        # Map ResearchMetrics fields; analytics not in schema → unavailable.
        total_return: Any = _UNAVAILABLE
        if metrics and metrics.get("start_capital") is not None and metrics.get(
            "end_capital"
        ) is not None:
            try:
                start_cap = Decimal(str(metrics["start_capital"]))
                end_cap = Decimal(str(metrics["end_capital"]))
                if start_cap != 0:
                    total_return = str((end_cap - start_cap) / start_cap)
            except (ArithmeticError, ValueError, TypeError):
                total_return = _UNAVAILABLE

        return {
            "total_return": total_return,
            "cagr": _UNAVAILABLE,
            "sharpe": _UNAVAILABLE,
            "sortino": _UNAVAILABLE,
            "max_drawdown": present("max_drawdown"),
            "profit_factor": present("profit_factor"),
            "win_rate": present("hit_rate"),
            "trade_count": present("closed_trades"),
            "fees": present("fees"),
            "slippage_costs": present("slippage_costs"),
            "funding_costs": present("funding_costs"),
            "net_pnl": present("net_pnl"),
            "gross_pnl": present("gross_pnl"),
            "expectancy": present("expectancy"),
            "avg_win": present("avg_win"),
            "avg_loss": present("avg_loss"),
            "benchmark_result": present("benchmark_result"),
            "status": present("status") if metrics else _UNAVAILABLE,
        }

    def _equity_series(
        self, equity: list[Any] | None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not equity:
            return [], []
        points: list[dict[str, Any]] = []
        for row in equity:
            if not isinstance(row, dict):
                continue
            eq = row.get("equity")
            ts = row.get("timestamp") or row.get("time") or row.get("as_of")
            if eq is None:
                continue
            try:
                eq_f = float(str(eq))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(eq_f):
                continue
            points.append({"t": str(ts) if ts is not None else "", "equity": eq_f})

        drawdown: list[dict[str, Any]] = []
        peak = None
        for p in points:
            eq = p["equity"]
            peak = eq if peak is None else max(peak, eq)
            dd = 0.0 if peak == 0 else (eq - peak) / peak
            drawdown.append({"t": p["t"], "drawdown": dd})
        return points, drawdown
