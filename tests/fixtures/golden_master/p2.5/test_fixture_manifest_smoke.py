"""Smoke: P2.5 golden-master fixture manifest is complete and hash-consistent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "fixture-manifest.json"
IO_PATH = ROOT / "expected-io-inventory.json"
DOCS_MANIFEST = (
    Path(__file__).resolve().parents[4]
    / "docs"
    / "p4"
    / "p2.5-production-baseline-manifest.md"
)


def test_fixture_manifest_fields_and_hashes() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema"] == "p2.5-golden-master-fixtures-v1"
    assert manifest["freeze_commit"] == "13a62f18d516dc50cbe0d1d3ba8764ed346311e1"
    assert manifest["tag"] == "p2.5-production-baseline"
    assert len(manifest["files"]) >= 5
    for entry in manifest["files"]:
        path = Path(entry["fixture_copy"])
        assert path.is_file(), entry["fixture_copy"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == entry["sha256"], entry["path"]


def test_expected_io_inventory_symbols_and_paper_only() -> None:
    inventory = json.loads(IO_PATH.read_text(encoding="utf-8"))
    assert inventory["supported_symbols"] == ["BTC", "ETH", "SOL"]
    assert inventory["live_execution"] is False
    assert inventory["execution_mode"] == "paper_only"
    assert inventory["inputs_to_freeze"]
    assert inventory["outputs_to_freeze"]


def test_docs_baseline_manifest_present() -> None:
    text = DOCS_MANIFEST.read_text(encoding="utf-8")
    assert "13a62f18d516dc50cbe0d1d3ba8764ed346311e1" in text
    assert "p2.5-production-baseline" in text
    assert "no live" in text.lower() or "No live" in text or "no live execution" in text.lower()
