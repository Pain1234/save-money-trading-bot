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
  ->  Seq Scan on paper_fills  (cost=0.00..10.00 rows=1000 width=100) (actual time=0.010..0.040 rows=10 loops=1)
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


def test_layer_c_summarize_marks_empty_as_not_measured() -> None:
    layer_c = _load("layer_c2", "scripts/measure_dashboard_layer_c_api.py")
    summary = layer_c.summarize_route("events", "/api/v1/events", [])
    assert summary.status == "NOT_MEASURED"


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
    assert "nicht automatisch schlecht" in doc.lower() or "not automatically bad" in doc.lower()
    assert "Vorher-/Nachher" in doc or "before/after" in doc.lower()
    assert "10.000" in doc or "10k" in doc.lower()
