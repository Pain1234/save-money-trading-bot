"""Governance checks for P5 public/private artifact boundary (#181)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DOC = ROOT / "docs" / "research" / "p5" / "P5_PUBLIC_PRIVATE_ARTIFACTS.md"
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
GITIGNORE = ROOT / ".gitignore"


def test_p5_private_storage_doc_names_private_repo() -> None:
    text = ARTIFACTS_DOC.read_text(encoding="utf-8")
    assert "save-money-trading-bot-private-research" in text
    assert "Public CI never checks out private" in text or "never checks out" in text.lower()
    assert "Forbidden paths" in text
    assert "#200" in text and "#204" in text and "#205" in text


def test_pr_template_includes_p5_leakage_checklist() -> None:
    text = PR_TEMPLATE.read_text(encoding="utf-8")
    assert "Private-Edge Leakage" in text or "private P5" in text.lower()
    assert "save-money-trading-bot-private-research" in text


def test_gitignore_blocks_private_research_mirrors() -> None:
    text = GITIGNORE.read_text(encoding="utf-8")
    assert "save-money-trading-bot-private-research/" in text
    assert "artifacts/research/**" in text
