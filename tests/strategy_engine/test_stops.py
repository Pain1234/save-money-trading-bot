"""Unit tests for ATR stops."""

from decimal import Decimal

from strategy_engine.models import StrategyParameters, TrailingStopState
from strategy_engine.stops import (
    compute_initial_stop,
    initialize_trailing_stop,
    update_trailing_stop,
)


class TestInitialStop:
    def test_initial_stop_formula(self) -> None:
        params = StrategyParameters()
        stop = compute_initial_stop(Decimal("95000"), Decimal("2400"), params)
        assert stop == Decimal("89000")


class TestTrailingStop:
    def test_trailing_stop_rises(self) -> None:
        params = StrategyParameters()
        stop_initial = compute_initial_stop(Decimal("95000"), Decimal("2400"), params)
        state = initialize_trailing_stop(
            Decimal("95000"), Decimal("2400"), stop_initial, params
        )
        updated = update_trailing_stop(
            state, Decimal("98000"), Decimal("2200"), params
        )
        assert updated.trail_stop > state.trail_stop
        assert updated.trail_stop == Decimal("91400")

    def test_trailing_stop_never_decreases(self) -> None:
        params = StrategyParameters()
        stop_initial = compute_initial_stop(Decimal("95000"), Decimal("2400"), params)
        state = initialize_trailing_stop(
            Decimal("95000"), Decimal("2400"), stop_initial, params
        )
        state = update_trailing_stop(state, Decimal("98000"), Decimal("2200"), params)
        higher_trail = state.trail_stop
        decreased = update_trailing_stop(
            state, Decimal("97000"), Decimal("5000"), params
        )
        assert decreased.trail_stop >= higher_trail
        assert decreased.trail_stop == higher_trail

    def test_trailing_update_sequence(self) -> None:
        """Verify spec §7.3 example."""
        params = StrategyParameters()
        stop_initial = Decimal("89000")
        state = TrailingStopState(
            entry_price=Decimal("95000"),
            stop_initial=stop_initial,
            highest_close=Decimal("95000"),
            trail_stop=stop_initial,
            effective_stop=stop_initial,
        )
        updated = update_trailing_stop(
            state, Decimal("98000"), Decimal("2200"), params
        )
        assert updated.highest_close == Decimal("98000")
        assert updated.trail_stop == Decimal("91400")
        assert updated.effective_stop == Decimal("91400")
