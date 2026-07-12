"""Helpers for market event bridge tests with commit/ack semantics."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from paper_trading.event_fairness import MarketEventGroupState
from paper_trading.market_events import BridgePollResult, MarketEventBridge


def wire_fairness_repo_mock(repo: MagicMock) -> dict[str, object]:
    """Attach in-memory fairness persistence behavior to a repository mock."""
    fairness_cursor = {"value": 0}
    group_states: dict[str, MarketEventGroupState] = {}

    repo.get_fairness_group_rotation_cursor.side_effect = lambda: fairness_cursor["value"]
    repo.set_fairness_group_rotation_cursor.side_effect = (
        lambda *, cursor, updated_at: fairness_cursor.update(value=cursor)
    )
    repo.list_market_event_group_states.side_effect = lambda: dict(group_states)
    repo.delete_market_event_group_state.side_effect = lambda group_key: group_states.pop(
        group_key,
        None,
    )

    def upsert_group_deferred(
        *,
        group_key: str,
        event_type: str,
        group_time: datetime,
        next_attempt_at: datetime,
        defer_count: int,
        updated_at: datetime,
    ) -> None:
        group_states[group_key] = MarketEventGroupState(
            group_key=group_key,
            event_type=event_type,
            group_time=group_time,
            next_attempt_at=next_attempt_at,
            defer_count=defer_count,
        )

    repo.upsert_market_event_group_deferred.side_effect = upsert_group_deferred
    return {"fairness_cursor": fairness_cursor, "group_states": group_states}


def poll_commit_ack(
    bridge: MarketEventBridge,
    repo,
    evaluation_time,
) -> BridgePollResult:
    result = bridge.process_after_poll(evaluation_time)
    repo.session.commit()
    bridge.acknowledge_committed(result.events_to_ack)
    bridge.acknowledge_terminal_failed_committed(result.events_terminal_failed)
    return result


def poll_without_ack(bridge: MarketEventBridge, evaluation_time) -> BridgePollResult:
    return bridge.process_after_poll(evaluation_time)


def ack_result(bridge: MarketEventBridge, result: BridgePollResult) -> None:
    bridge.acknowledge_committed(result.events_to_ack)
    bridge.acknowledge_terminal_failed_committed(result.events_terminal_failed)
