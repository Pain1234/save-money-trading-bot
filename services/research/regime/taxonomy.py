"""Regime taxonomy enums for P4.9 classifier (Issue #285).

Extends the P5-03 (#199) monthly trend/vol contract with a three-way
volatility axis and an explicit transition/event layer. Private Strategy V1
thresholds stay out of this module; freeze binding is [#294].
"""

from __future__ import annotations

from typing import Literal

TrendLabel = Literal["BULL", "BEAR", "SIDEWAYS", "INSUFFICIENT"]
VolLabel = Literal["LOW_VOL", "NORMAL_VOL", "HIGH_VOL", "INSUFFICIENT"]
EventLabel = Literal[
    "TRANSITION_IN",
    "TRANSITION_OUT",
    "STABLE_REGIME",
    "INSUFFICIENT",
]

TREND_LABELS: frozenset[str] = frozenset(
    {"BULL", "BEAR", "SIDEWAYS", "INSUFFICIENT"}
)
VOL_LABELS: frozenset[str] = frozenset(
    {"LOW_VOL", "NORMAL_VOL", "HIGH_VOL", "INSUFFICIENT"}
)
EVENT_LABELS: frozenset[str] = frozenset(
    {"TRANSITION_IN", "TRANSITION_OUT", "STABLE_REGIME", "INSUFFICIENT"}
)
