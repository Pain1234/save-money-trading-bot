"""OAT contiguity graph for parameter-area classification (#290)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class AxisPoint:
    child_id: str
    axis: str
    value: Decimal
    stable: bool


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def changed_axes(
    frozen: Mapping[str, Any], params: Mapping[str, Any]
) -> tuple[str, ...]:
    keys = sorted(
        k
        for k in set(frozen) | set(params)
        if k != "strategy_id" and frozen.get(k) != params.get(k)
    )
    return tuple(keys)


def build_axis_points(
    *,
    frozen_child_id: str,
    frozen_parameters: Mapping[str, Any],
    frozen_stable: bool,
    neighbors: Sequence[Mapping[str, Any]],
) -> dict[str, list[AxisPoint]]:
    """Group OAT neighbors by single changed axis; include frozen at each axis."""
    by_axis: dict[str, list[AxisPoint]] = {}
    for row in neighbors:
        params = row["parameters"]
        axes = changed_axes(frozen_parameters, params)
        if len(axes) != 1:
            # Multi-axis / empty change — not part of OAT contiguous regions.
            continue
        axis = axes[0]
        point = AxisPoint(
            child_id=str(row["child_id"]),
            axis=axis,
            value=_to_decimal(params[axis]),
            stable=bool(row["stable"]),
        )
        by_axis.setdefault(axis, []).append(point)

    for axis, points in list(by_axis.items()):
        if axis not in frozen_parameters:
            continue
        frozen_point = AxisPoint(
            child_id=frozen_child_id,
            axis=axis,
            value=_to_decimal(frozen_parameters[axis]),
            stable=frozen_stable,
        )
        # Avoid duplicate frozen if somehow present.
        if not any(p.child_id == frozen_child_id for p in points):
            points.append(frozen_point)
        points.sort(key=lambda p: (p.value, p.child_id))
        by_axis[axis] = points
    return by_axis


def max_contiguous_stable_run(points: Sequence[AxisPoint]) -> int:
    """Longest run of consecutive stable points along a sorted axis."""
    best = 0
    current = 0
    for point in points:
        if point.stable:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def measure_contiguous_regions(
    by_axis: Mapping[str, Sequence[AxisPoint]],
) -> dict[str, Any]:
    """Compute plateau size and per-axis contiguous stable lengths."""
    axis_runs: dict[str, int] = {}
    for axis, points in sorted(by_axis.items()):
        axis_runs[axis] = max_contiguous_stable_run(points)
    plateau_size = max(axis_runs.values()) if axis_runs else 0
    best_axis = None
    if axis_runs:
        best_axis = max(axis_runs.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return {
        "plateau_size": plateau_size,
        "best_axis": best_axis,
        "axis_contiguous_stable": axis_runs,
        "contiguous_region_rule": "oat_axis_adjacent_including_frozen_v1",
    }
