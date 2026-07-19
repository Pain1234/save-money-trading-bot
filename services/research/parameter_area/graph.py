"""OAT contiguity graph for parameter-area classification (#290)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class AxisPoint:
    child_id: str
    axis: str
    value: Decimal
    stable: bool


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def parameters_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Compare parameter maps; numeric strings/ints compare via Decimal."""
    keys = (set(left) | set(right)) - {"strategy_id"}
    for key in keys:
        if key not in left or key not in right:
            return False
        a = left[key]
        b = right[key]
        if a == b:
            continue
        try:
            if Decimal(str(a)) == Decimal(str(b)):
                continue
        except (InvalidOperation, ValueError):
            pass
        return False
    return True


def changed_axes(
    frozen: Mapping[str, Any], params: Mapping[str, Any]
) -> tuple[str, ...]:
    out: list[str] = []
    for key in sorted((set(frozen) | set(params)) - {"strategy_id"}):
        if key not in frozen or key not in params:
            out.append(key)
            continue
        if not parameters_equal({key: frozen[key]}, {key: params[key]}):
            out.append(key)
    return tuple(out)


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
        if not any(p.child_id == frozen_child_id for p in points):
            points.append(frozen_point)
        points.sort(key=lambda p: (p.value, p.child_id))
        by_axis[axis] = points
    return by_axis


def contiguous_stable_through_frozen(
    points: Sequence[AxisPoint], *, frozen_child_id: str
) -> int:
    """Length of the stable run that includes the frozen point (0 if frozen unstable)."""
    idx = next(
        (i for i, point in enumerate(points) if point.child_id == frozen_child_id),
        None,
    )
    if idx is None:
        return 0
    if not points[idx].stable:
        return 0
    left = idx
    while left > 0 and points[left - 1].stable:
        left -= 1
    right = idx
    while right + 1 < len(points) and points[right + 1].stable:
        right += 1
    return right - left + 1


def measure_contiguous_regions(
    by_axis: Mapping[str, Sequence[AxisPoint]],
    *,
    frozen_child_id: str = "frozen",
) -> dict[str, Any]:
    """Plateau size = longest stable run that includes the frozen point."""
    axis_runs: dict[str, int] = {}
    for axis, points in sorted(by_axis.items()):
        axis_runs[axis] = contiguous_stable_through_frozen(
            points, frozen_child_id=frozen_child_id
        )
    plateau_size = max(axis_runs.values()) if axis_runs else 0
    # Frozen alone (no OAT axes) still counts as size 1 when stable — handled by caller.
    best_axis = None
    if axis_runs:
        best_axis = max(axis_runs.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return {
        "plateau_size": plateau_size,
        "best_axis": best_axis,
        "axis_contiguous_stable": axis_runs,
        "contiguous_region_rule": "oat_axis_adjacent_including_frozen_v1",
        "plateau_includes_frozen": plateau_size > 0,
    }
