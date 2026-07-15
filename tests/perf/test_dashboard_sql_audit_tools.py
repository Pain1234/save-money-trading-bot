"""Unit tests for Issue #101 audit harness scripts (no live network required)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(module_name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Python 3.14 dataclasses look up cls.__module__ in sys.modules during
    # class creation; register before exec_module.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_events_payload_analysis_splits_payload_bytes() -> None:
    layer_c = _load("layer_c", "scripts/measure_dashboard_layer_c_api.py")
    payload = {"detail": "x" * 1000, "nested": {"a": 1}}
    body = json.dumps(
        {
            "items": [
                {
                    "event_type": "FAIL",
                    "aggregate_type": "order",
                    "created_at": "2026-07-15T00:00:00Z",
                    "payload_json": payload,
                }
            ],
            "next_cursor": None,
            "limit": 50,
        }
    ).encode("utf-8")
    payload_bytes, share = layer_c.analyze_events_payload(body)
    assert payload_bytes is not None and payload_bytes > 0
    assert share is not None and 0.0 < share <= 1.0
    assert payload_bytes < len(body)


def test_explain_parser_extracts_execution_and_buffers() -> None:
    explain = _load("explain", "scripts/audit_dashboard_sql_explain.py")
    sample = """
Limit  (cost=0.00..1.50 rows=50 width=100) (actual time=0.020..0.050 rows=10 loops=1)
  Buffers: shared hit=12 read=3
  ->  Seq Scan on paper_fills  (cost=0.00..10.00 rows=1000 width=100)
      (actual time=0.010..0.040 rows=10 loops=1)
        Filter: (symbol IS NOT NULL)
        Rows Removed by Filter: 2
Planning Time: 0.123 ms
Execution Time: 0.456 ms
"""
    metrics = explain._parse_explain(sample)
    assert metrics.status == "MEASURED"
    assert metrics.execution_ms == 0.456
    assert metrics.planning_ms == 0.123
    assert metrics.shared_hit_blocks == 12
    assert metrics.shared_read_blocks == 3
    assert metrics.rows_removed_by_filter == 2
    assert metrics.plan_node is not None


def test_cursor_anchor_uses_last_row_of_first_page() -> None:
    explain = _load("explain_anchor", "scripts/audit_dashboard_sql_explain.py")
    rows = [
        {"fill_time": "2026-07-15T10:00:00+00:00", "fill_id": "aaa"},
        {"fill_time": "2026-07-15T09:00:00+00:00", "fill_id": "bbb"},
        {"fill_time": "2026-07-15T08:00:00+00:00", "fill_id": "ccc"},
    ]
    anchor = explain._anchor_from_rows(rows, ("fill_time", "fill_id"))
    assert anchor is not None
    assert anchor["ts"] == "2026-07-15T08:00:00+00:00"
    assert anchor["id"] == "ccc"


def test_cursor_anchor_empty_page_returns_none() -> None:
    explain = _load("explain_anchor2", "scripts/audit_dashboard_sql_explain.py")
    assert explain._anchor_from_rows([], ("fill_time", "fill_id")) is None


def test_layer_c_summarize_marks_empty_as_not_measured() -> None:
    layer_c = _load("layer_c2", "scripts/measure_dashboard_layer_c_api.py")
    summary = layer_c.summarize_route("events", "/api/v1/events", [])
    assert summary.status == "NOT_MEASURED"


def test_layer_c_summarize_partial_without_perf_headers() -> None:
    layer_c = _load("layer_c3", "scripts/measure_dashboard_layer_c_api.py")
    sample = layer_c.RouteSample(
        status_code=200,
        client_total_ms=12.0,
        header_total_ms=None,
        header_db_ms=None,
        header_query_count=None,
        response_bytes=100,
        correlation_id=None,
    )
    summary = layer_c.summarize_route("status", "/api/v1/status", [sample])
    assert summary.status == "PARTIAL"
    assert summary.warm_client_p95_ms == 12.0
    assert summary.warm_header_total_p95_ms is None


def test_layer_c_summarize_measured_with_all_perf_headers() -> None:
    layer_c = _load("layer_c4", "scripts/measure_dashboard_layer_c_api.py")
    sample = layer_c.RouteSample(
        status_code=200,
        client_total_ms=20.0,
        header_total_ms=18.0,
        header_db_ms=5.0,
        header_query_count=2,
        response_bytes=200,
        correlation_id="cid",
    )
    summary = layer_c.summarize_route("wallet", "/api/v1/wallet", [sample])
    assert summary.status == "MEASURED"
    assert summary.warm_header_db_p95_ms == 5.0
    assert summary.warm_query_count_p95 == 2.0


def test_ssr_rejects_login_redirect_html() -> None:
    ssr = _load("layer_b", "scripts/measure_dashboard_ssr.py")
    login_html = b"<html><body>Sign in</body></html>"
    assert not ssr.is_authenticated_dashboard(
        "/dashboard",
        "https://bot.example/login",
        login_html,
    )


def test_ssr_accepts_authenticated_dashboard_marker() -> None:
    ssr = _load("layer_b2", "scripts/measure_dashboard_ssr.py")
    body = b"<html><body>Paper Trading Monitor</body></html>"
    assert ssr.is_authenticated_dashboard(
        "/dashboard/status",
        "https://bot.example/dashboard/status",
        body,
    )


def test_ssr_rejects_wrong_final_path() -> None:
    ssr = _load("layer_b3", "scripts/measure_dashboard_ssr.py")
    body = b"<html><body>Paper Trading Monitor</body></html>"
    assert not ssr.is_authenticated_dashboard(
        "/dashboard",
        "https://bot.example/dashboard/status",
        body,
    )


def test_sql_audit_doc_has_required_sections() -> None:
    doc = (REPO_ROOT / "docs" / "operations" / "dashboard-sql-audit.md").read_text(
        encoding="utf-8"
    )
    required = [
        "1. Scope",
        "2. Architektur und Messpunkte",
        "3. Testumgebung",
        "4. Railway-Netzwerkpfad",
        "5. Browser- und sichtbarer-Content-Messung",
        "6. Next.js-/SSR-Messung",
        "7. FastAPI-Messung",
        "8. PostgreSQL-Messung",
        "9. vorhandene Tabellen und Indizes",
        "10. Route-für-Route-Ergebnisse",
        "11. Events-Payload-Analyse",
        "12. Top-3-Bottlenecks",
        "13. geprüfte Optimierungskandidaten",
        "14. bestätigte Empfehlungen",
        "15. verworfene Empfehlungen",
        "16. offene Messungen",
        "17. Vorher-/Nachher-Protokoll",
        "NOT_MEASURED",
        "Seq Scan",
        "payload_json",
    ]
    for section in required:
        assert section in doc, f"missing section/marker: {section}"


def test_index_gate_rejects_seq_scan_only_rule() -> None:
    doc = (REPO_ROOT / "docs" / "operations" / "dashboard-sql-audit.md").read_text(
        encoding="utf-8"
    )
    assert (
        "nicht automatisch schlecht" in doc.lower()
        or "not automatically bad" in doc.lower()
    )
    assert "Vorher-/Nachher" in doc or "before/after" in doc.lower()
    assert "10.000" in doc or "10k" in doc.lower()


def test_prepare_session_uses_set_transaction_read_only() -> None:
    import inspect

    explain = _load("explain_ro", "scripts/audit_dashboard_sql_explain.py")
    source = inspect.getsource(explain._prepare_session)
    assert 'text("SET TRANSACTION READ ONLY")' in source
    assert "SET LOCAL statement_timeout" in source
    assert 'text("SET default_transaction_read_only' not in source
    assert "SET TRANSACTION READ ONLY" in source.split("conn.execute")[1]


def test_layer_a_source_avoids_skeleton_timeout_before_heading() -> None:
    source = (
        REPO_ROOT / "tests" / "e2e" / "dashboard-layer-a-perf.spec.ts"
    ).read_text(encoding="utf-8")
    assert "Promise.race" in source
    assert "installLcpObserver" in source
    assert "PerformanceObserver" in source
    assert "browser.newContext()" in source
    assert "/dashboard/status" in source
    # Must not await skeleton before recording heading.
    assert "await skeletonWatch" not in source
    assert "Same document" in source or "same document" in source.lower()
