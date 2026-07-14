"""Pytest path setup — avoid shadowing by tests/strategy_engine package name."""

from __future__ import annotations

import sys
from pathlib import Path

pytest_plugins = ["tests.postgres_fixtures"]

_SERVICES = Path(__file__).resolve().parents[1] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))
