#!/usr/bin/env python3
"""Layer D — PostgreSQL EXPLAIN (ANALYZE, BUFFERS) for dashboard history routes.

Issue #101. Read-only analysis. Does **not** create indexes or migrations.

Usage:
    export PAPER_TRADING_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test
    python scripts/audit_dashboard_sql_explain.py \\
        --output docs/operations/dashboard-layer-d-explain.json

Railway: run from a service/probe inside the same environment that can reach
the private Postgres URL. Do not publish the DB.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

# Statements mirror ``PaperTradingRepository.list_*`` ORDER BY / keyset filters.
# Cursor page uses a representative OR-predicate; bind values come from a first-page sample.
HISTORY_QUERIES: tuple[dict[str, Any], ...] = (
    {
        "route": "/api/v1/fills",
        "table": "paper_fills",
        "first_page_sql": (
            "SELECT * FROM paper_fills "
            "ORDER BY fill_time DESC, fill_id DESC "
            "LIMIT 50"
        ),
        "cursor_page_sql_template": (
            "SELECT * FROM paper_fills "
            "WHERE fill_time < '{ts}' OR (fill_time = '{ts}' AND fill_id < '{id}') "
            "ORDER BY fill_time DESC, fill_id DESC "
            "LIMIT 50"
        ),
        "cursor_keys": ("fill_time", "fill_id"),
        "existing_indexes": ["ix_paper_fills_symbol_time (symbol, fill_time)"],
        "candidate_index": "(fill_time, fill_id)",
    },
    {
        "route": "/api/v1/orders",
        "table": "paper_orders",
        "first_page_sql": (
            "SELECT * FROM paper_orders "
            "ORDER BY created_at DESC, paper_order_id DESC "
            "LIMIT 50"
        ),
        "cursor_page_sql_template": (
            "SELECT * FROM paper_orders "
            "WHERE created_at < '{ts}' OR (created_at = '{ts}' AND paper_order_id < '{id}') "
            "ORDER BY created_at DESC, paper_order_id DESC "
            "LIMIT 50"
        ),
        "cursor_keys": ("created_at", "paper_order_id"),
        "existing_indexes": [
            "ix_paper_orders_status_fill_time (status, expected_fill_time)",
            "ix_paper_orders_symbol (symbol)",
        ],
        "candidate_index": "(created_at, paper_order_id)",
    },
    {
        "route": "/api/v1/equity",
        "table": "portfolio_snapshots",
        "first_page_sql": (
            "SELECT * FROM portfolio_snapshots "
            "ORDER BY evaluation_time DESC, snapshot_id DESC "
            "LIMIT 100"
        ),
        "cursor_page_sql_template": (
            "SELECT * FROM portfolio_snapshots "
            "WHERE evaluation_time < '{ts}' OR "
            "(evaluation_time = '{ts}' AND snapshot_id < '{id}') "
            "ORDER BY evaluation_time DESC, snapshot_id DESC "
            "LIMIT 100"
        ),
        "cursor_keys": ("evaluation_time", "snapshot_id"),
        "existing_indexes": ["ix_portfolio_snapshots_eval_time (evaluation_time)"],
        "candidate_index": "(evaluation_time, snapshot_id)",
    },
    {
        "route": "/api/v1/events",
        "table": "audit_events",
        "first_page_sql": (
            "SELECT * FROM audit_events "
            "ORDER BY created_at DESC, event_id DESC "
            "LIMIT 50"
        ),
        "cursor_page_sql_template": (
            "SELECT * FROM audit_events "
            "WHERE created_at < '{ts}' OR (created_at = '{ts}' AND event_id < '{id}') "
            "ORDER BY created_at DESC, event_id DESC "
            "LIMIT 50"
        ),
        "cursor_keys": ("created_at", "event_id"),
        "existing_indexes": [
            "ix_audit_events_created (created_at)",
            "ix_audit_events_type (event_type)",
            "ix_audit_events_aggregate (aggregate_type, aggregate_id)",
            "ix_audit_events_cycle (cycle_id)",
        ],
        "candidate_index": "(created_at, event_id)",
    },
    {
        "route": "/api/v1/scheduler-runs",
        "table": "scheduler_runs",
        "first_page_sql": (
            "SELECT * FROM scheduler_runs "
            "ORDER BY scheduled_for DESC, run_id DESC "
            "LIMIT 50"
        ),
        "cursor_page_sql_template": (
            "SELECT * FROM scheduler_runs "
            "WHERE scheduled_for < '{ts}' OR "
            "(scheduled_for = '{ts}' AND run_id < '{id}') "
            "ORDER BY scheduled_for DESC, run_id DESC "
            "LIMIT 50"
        ),
        "cursor_keys": ("scheduled_for", "run_id"),
        "existing_indexes": [
            "ix_scheduler_runs_running (status, started_at)",
            "ix_scheduler_runs_recovery_of",
            "ix_scheduler_runs_soak_run_id",
        ],
        "candidate_index": "(scheduled_for, run_id)",
    },
    {
        "route": "/api/v1/positions",
        "table": "paper_positions",
        "first_page_sql": (
            "SELECT * FROM paper_positions "
            "ORDER BY opened_at DESC, position_id DESC "
            "LIMIT 50"
        ),
        "cursor_page_sql_template": (
            "SELECT * FROM paper_positions "
            "WHERE opened_at < '{ts}' OR "
            "(opened_at = '{ts}' AND position_id < '{id}') "
            "ORDER BY opened_at DESC, position_id DESC "
            "LIMIT 50"
        ),
        "cursor_keys": ("opened_at", "position_id"),
        "existing_indexes": [
            "ix_paper_positions_status (status)",
            "uq_paper_positions_open_symbol (partial)",
        ],
        "candidate_index": "(opened_at, position_id)",
    },
)


@dataclass
class PlanMetrics:
    status: str
    execution_ms: float | None = None
    planning_ms: float | None = None
    plan_node: str | None = None
    actual_rows: int | None = None
    planned_rows: int | None = None
    shared_hit_blocks: int | None = None
    shared_read_blocks: int | None = None
    sort_method: str | None = None
    sort_space_used: str | None = None
    rows_removed_by_filter: int | None = None
    raw_excerpt: str | None = None
    note: str = ""


def _parse_explain(text: str) -> PlanMetrics:
    exec_m = re.search(r"Execution Time:\s*([0-9.]+)\s*ms", text)
    plan_m = re.search(r"Planning Time:\s*([0-9.]+)\s*ms", text)
    rows_m = re.search(r"\(actual time=.*?rows=(\d+)", text)
    planned_m = re.search(r"\(cost=.*?rows=(\d+)", text)
    hit_m = re.search(r"shared hit=(\d+)", text)
    # EXPLAIN may say "shared hit=N read=M" or "shared hit=N shared read=M".
    read_m = re.search(r"shared read=(\d+)", text) or re.search(
        r"shared hit=\d+\s+read=(\d+)", text
    )
    sort_m = re.search(r"Sort Method:\s*(\S+)", text)
    sort_space_m = re.search(r"Sort Method:[^\n]*?Memory:\s*([^\n]+)", text)
    filter_m = re.search(r"Rows Removed by Filter:\s*(\d+)", text)
    node_m = re.search(
        r"->\s*((?:Index|Seq|Bitmap|Limit|Sort|Gather)[^\n(]+)",
        text,
    )
    top_node = None
    for pattern in (
        r"^\s*((?:Limit|Sort|Index Scan|Index Only Scan|Seq Scan|Bitmap)[^\n(]+)",
    ):
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            top_node = m.group(1).strip()
            break
    return PlanMetrics(
        status="MEASURED",
        execution_ms=float(exec_m.group(1)) if exec_m else None,
        planning_ms=float(plan_m.group(1)) if plan_m else None,
        plan_node=top_node or (node_m.group(1).strip() if node_m else None),
        actual_rows=int(rows_m.group(1)) if rows_m else None,
        planned_rows=int(planned_m.group(1)) if planned_m else None,
        shared_hit_blocks=int(hit_m.group(1)) if hit_m else None,
        shared_read_blocks=int(read_m.group(1)) if read_m else None,
        sort_method=sort_m.group(1).strip() if sort_m else None,
        sort_space_used=sort_space_m.group(1).strip() if sort_space_m else None,
        rows_removed_by_filter=int(filter_m.group(1)) if filter_m else None,
        raw_excerpt=text[:2000],
    )


def _row_count(conn: Any, table: str) -> int:
    from sqlalchemy import text

    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def _fetch_cursor_anchor(conn: Any, sql: str, keys: tuple[str, str]) -> dict[str, str] | None:
    from sqlalchemy import text

    row = conn.execute(text(sql)).mappings().first()
    if row is None:
        return None
    ts_key, id_key = keys
    ts_val = row[ts_key]
    id_val = row[id_key]
    if hasattr(ts_val, "isoformat"):
        ts_str = ts_val.isoformat()
    else:
        ts_str = str(ts_val)
    return {"ts": ts_str, "id": str(id_val)}


def _explain(conn: Any, sql: str) -> PlanMetrics:
    from sqlalchemy import text

    result = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}"))
    lines = [str(r[0]) for r in result]
    return _parse_explain("\n".join(lines))


def run_audit(database_url: str) -> dict[str, Any]:
    from paper_trading.db.session import create_db_engine

    engine = create_db_engine(database_url, application_name="dashboard-sql-audit")
    routes: list[dict[str, Any]] = []
    try:
        for spec in HISTORY_QUERIES:
            # Fresh connection per route so one SQL error cannot abort siblings.
            with engine.connect() as conn:
                try:
                    total_rows = _row_count(conn, spec["table"])
                    first = _explain(conn, spec["first_page_sql"])
                    anchor = _fetch_cursor_anchor(conn, spec["first_page_sql"], spec["cursor_keys"])
                    if anchor is None:
                        cursor = PlanMetrics(
                            status="NOT_MEASURED",
                            note="empty table — no cursor page",
                        )
                        cursor_sql = None
                    else:
                        cursor_sql = spec["cursor_page_sql_template"].format(
                            ts=anchor["ts"],
                            id=anchor["id"],
                        )
                        cursor = _explain(conn, cursor_sql)
                    routes.append(
                        {
                            "route": spec["route"],
                            "table": spec["table"],
                            "rows_total": total_rows,
                            "existing_indexes": spec["existing_indexes"],
                            "candidate_index": spec["candidate_index"],
                            "index_gate": (
                                "Propose index only if scan/sort/filter is a material "
                                "share of route latency AND before/after on the same "
                                "representative dataset shows a real benefit. "
                                "Seq Scan alone (even at >10k rows) is not sufficient."
                            ),
                            "first_page": asdict(first),
                            "cursor_page": asdict(cursor),
                            "first_page_sql": spec["first_page_sql"],
                            "cursor_page_sql": cursor_sql,
                            "recommendation_status": "FOLLOW_UP_REQUIRED",
                            "recommendation": (
                                "No index migration in this audit. Record before/after "
                                "plans before opening a separate migration issue."
                            ),
                        }
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001 — capture per-route failures
                    conn.rollback()
                    routes.append(
                        {
                            "route": spec["route"],
                            "table": spec["table"],
                            "rows_total": None,
                            "status": "NOT_MEASURED",
                            "note": f"{type(exc).__name__}: {exc}",
                            "existing_indexes": spec["existing_indexes"],
                            "candidate_index": spec["candidate_index"],
                            "recommendation_status": "FOLLOW_UP_REQUIRED",
                        }
                    )
    finally:
        engine.dispose()

    return {
        "measurement": "layer_d_postgresql_explain",
        "issue": 101,
        "measured_at": datetime.now(UTC).isoformat(),
        "status": (
            "MEASURED"
            if any(r.get("first_page", {}).get("status") == "MEASURED" for r in routes)
            else "NOT_MEASURED"
        ),
        "postgres_sort_notes": [
            "DESC is not required for a fully backward-scannable B-tree.",
            "Column order matching keyset pagination matters more than DESC markers.",
            "Do not rewrite OR keyset predicates to tuple compares without measured gain.",
        ],
        "routes": routes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "PAPER_TRADING_DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test",
        ),
    )
    parser.add_argument(
        "--output",
        default="docs/operations/dashboard-layer-d-explain.json",
    )
    args = parser.parse_args(argv)
    try:
        report = run_audit(args.database_url)
    except Exception as exc:  # noqa: BLE001
        report = {
            "measurement": "layer_d_postgresql_explain",
            "issue": 101,
            "status": "NOT_MEASURED",
            "measured_at": datetime.now(UTC).isoformat(),
            "note": f"{type(exc).__name__}: {exc}",
            "routes": [],
        }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(f"Wrote {args.output} (status={report.get('status')})")
    return 0 if report.get("status") == "MEASURED" else 1


if __name__ == "__main__":
    # Ensure ``services/`` is importable when run as a script.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    services = os.path.join(repo_root, "services")
    if services not in sys.path:
        sys.path.insert(0, services)
    sys.exit(main())
