"""Tests for scripts/reconcile_accounting.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts import reconcile_accounting


def test_main_ok() -> None:
    config = MagicMock()
    config.database_url = "postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    config.paper_initial_equity = 100000
    engine = MagicMock()
    session = MagicMock()
    session_factory = MagicMock(return_value=session)

    with (
        patch.object(reconcile_accounting, "PaperTradingConfig") as mock_config_cls,
        patch.object(reconcile_accounting, "create_db_engine", return_value=engine),
        patch.object(reconcile_accounting, "create_session_factory", return_value=session_factory),
        patch.object(reconcile_accounting, "PaperTradingRepository"),
        patch.object(reconcile_accounting, "verify_accounting_independent", return_value=[]),
    ):
        mock_config_cls.from_env.return_value = config
        assert reconcile_accounting.main() == 0

    session.close.assert_called_once()
    engine.dispose.assert_called_once()


def test_main_reports_issues() -> None:
    config = MagicMock()
    config.database_url = "postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    config.paper_initial_equity = 100000
    engine = MagicMock()
    session = MagicMock()
    session_factory = MagicMock(return_value=session)

    with (
        patch.object(reconcile_accounting, "PaperTradingConfig") as mock_config_cls,
        patch.object(reconcile_accounting, "create_db_engine", return_value=engine),
        patch.object(reconcile_accounting, "create_session_factory", return_value=session_factory),
        patch.object(reconcile_accounting, "PaperTradingRepository"),
        patch.object(
            reconcile_accounting,
            "verify_accounting_independent",
            return_value=["wallet cash mismatch"],
        ),
    ):
        mock_config_cls.from_env.return_value = config
        assert reconcile_accounting.main() == 1

    session.close.assert_called_once()
    engine.dispose.assert_called_once()
