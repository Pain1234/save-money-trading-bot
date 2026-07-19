"""Classify parameter-area labels from neighborhood stats (#290)."""

from __future__ import annotations

from decimal import Decimal

from research.parameter_area.policy import ParameterAreaPolicy


def classify_parameter_area(
    *,
    policy: ParameterAreaPolicy,
    n_complete_neighbors: int,
    stable_share: Decimal,
    gate_pass_share: Decimal | None,
    gates_available: bool,
    plateau_size: int,
    frozen_stable: bool,
    plateau_includes_frozen: bool,
    any_stable_neighbor: bool,
    steepest_drop: Decimal | None,
) -> tuple[str, str]:
    """Return (classification, reason).

    BROAD/NARROW require a contiguous stable run that includes the frozen point.
    """
    if n_complete_neighbors < policy.min_complete_neighbors:
        return (
            "INSUFFICIENT_EVIDENCE",
            f"complete_neighbors={n_complete_neighbors} < "
            f"min_complete_neighbors={policy.min_complete_neighbors}",
        )

    if not frozen_stable:
        if any_stable_neighbor:
            return (
                "UNSTABLE",
                "frozen_unstable_despite_stable_neighbors",
            )
        return ("UNSTABLE", "no_stable_frozen_or_neighbors")

    # Isolated peak before steep-drop UNSTABLE.
    if frozen_stable and not any_stable_neighbor:
        return ("ISOLATED_PEAK", "frozen_stable_without_stable_neighbors")

    steep_warn = Decimal(policy.steep_drop_warn)
    if (
        steepest_drop is not None
        and steepest_drop > steep_warn
        and stable_share < Decimal(policy.narrow_min_stable_share)
    ):
        return (
            "UNSTABLE",
            f"steepest_drop={steepest_drop} exceeds warn={steep_warn} "
            f"with weak stable_share={stable_share}",
        )

    if not plateau_includes_frozen or plateau_size < policy.narrow_min_contiguous:
        if frozen_stable and not any_stable_neighbor:
            return ("ISOLATED_PEAK", "no_contiguous_frozen_plateau")
        if frozen_stable:
            return (
                "ISOLATED_PEAK",
                f"plateau_size={plateau_size} < "
                f"narrow_min_contiguous={policy.narrow_min_contiguous} "
                f"(frozen-inclusive)",
            )
        return (
            "UNSTABLE",
            f"plateau_size={plateau_size} < "
            f"narrow_min_contiguous={policy.narrow_min_contiguous}",
        )

    broad_share = Decimal(policy.broad_min_stable_share)
    narrow_share = Decimal(policy.narrow_min_stable_share)
    broad_gate = Decimal(policy.broad_min_gate_pass_share)

    if (
        plateau_size >= policy.broad_min_contiguous
        and plateau_includes_frozen
        and frozen_stable
        and stable_share >= broad_share
        and gates_available
        and gate_pass_share is not None
        and gate_pass_share >= broad_gate
    ):
        return (
            "BROAD_STABLE_PLATEAU",
            f"plateau_size={plateau_size}, stable_share={stable_share}, "
            f"gate_pass_share={gate_pass_share}",
        )

    if (
        plateau_size >= policy.narrow_min_contiguous
        and plateau_includes_frozen
        and frozen_stable
        and stable_share >= narrow_share
    ):
        return (
            "NARROW_STABLE_AREA",
            f"plateau_size={plateau_size}, stable_share={stable_share}, "
            f"gates_available={gates_available}",
        )

    if stable_share < narrow_share:
        return ("UNSTABLE", f"stable_share={stable_share} < narrow={narrow_share}")

    return (
        "INSUFFICIENT_EVIDENCE",
        "neighborhood_does_not_meet_documented_plateau_rules",
    )
