"""Shared Research API test authentication."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def research_write_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_WRITE_API_KEY", "research-test-key")
