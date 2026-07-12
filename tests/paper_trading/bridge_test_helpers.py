"""Helpers for market event bridge tests with commit/ack semantics."""

from __future__ import annotations

from paper_trading.market_events import BridgePollResult, MarketEventBridge


def poll_commit_ack(
    bridge: MarketEventBridge,
    repo,
    evaluation_time,
) -> BridgePollResult:
    result = bridge.process_after_poll(evaluation_time)
    repo.session.commit()
    bridge.acknowledge_committed(result.events_to_ack)
    return result


def poll_without_ack(bridge: MarketEventBridge, evaluation_time) -> BridgePollResult:
    return bridge.process_after_poll(evaluation_time)


def ack_result(bridge: MarketEventBridge, result: BridgePollResult) -> None:
    bridge.acknowledge_committed(result.events_to_ack)
