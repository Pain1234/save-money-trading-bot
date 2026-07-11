# ruff: noqa: E402
"""C3 regression: conflicts isolated by symbol and timeframe."""

from __future__ import annotations

from decimal import Decimal

from market_data.models import DataQualityStatus, MarketDataReasonCode, MarketSymbol
from market_data.repository import InMemoryCandleRepository
from market_data.service import MarketDataService

from tests.market_data.conftest import dt, make_daily, make_daily_series


def test_eth_conflict_does_not_invalidate_btc_bundle() -> None:
    btc_dailies = make_daily_series(35, symbol=MarketSymbol.BTC)
    eth_base = make_daily(day=dt(2024, 1, 1), symbol=MarketSymbol.ETH)
    eth_conflict = eth_base.model_copy(update={"close": Decimal("999")})

    repo = InMemoryCandleRepository()
    repo.upsert_many(btc_dailies)
    repo.upsert(eth_base)
    repo.upsert(eth_conflict)

    service = MarketDataService(repo)
    eval_time = btc_dailies[-1].close_time

    btc_bundle = service.build_strategy_bundle(
        MarketSymbol.BTC,
        eval_time,
        daily_minimum=21,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )
    eth_bundle = service.build_strategy_bundle(
        MarketSymbol.ETH,
        eval_time,
        daily_minimum=1,
        weekly_minimum=1,
        monthly_minimum=1,
        backfill=False,
    )

    assert btc_bundle.report.status == DataQualityStatus.VALID
    assert btc_bundle.is_usable is True
    assert eth_bundle.report.status == DataQualityStatus.INVALID
    assert MarketDataReasonCode.MD_DUPLICATE_CONFLICT in eth_bundle.report.reason_codes
