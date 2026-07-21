"""Independent wallet reconstruction from canonical persisted economic data."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from paper_trading.enums import PaperFillKind, PaperPositionStatus
from paper_trading.repository import PaperTradingRepository


@dataclass(frozen=True)
class ReconstructedWallet:
    cash: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    total_realized_pnl: Decimal
    open_margin: Decimal
    total_funding: Decimal


def reconstruct_wallet(
    repo: PaperTradingRepository,
    *,
    initial_cash: Decimal,
) -> ReconstructedWallet:
    """Rebuild wallet totals from paper_fills, paper_positions, and paper_wallet seed."""
    cash = initial_cash
    fees = Decimal("0")
    slippage = Decimal("0")
    realized = Decimal("0")

    positions_by_id = {p.position_id: p for p in repo.list_positions(limit=10_000)}

    for fill in repo.list_all_fills():
        fees += fill.fee
        slippage += fill.slippage
        if fill.fill_kind == PaperFillKind.ENTRY:
            cash -= fill.fee
            continue
        if fill.fill_kind != PaperFillKind.EXIT:
            continue
        if fill.position_id is None:
            continue
        position = positions_by_id.get(fill.position_id)
        if position is None:
            continue
        gross_pnl = (fill.fill_price - position.average_entry_price) * fill.quantity
        net_pnl = gross_pnl - fill.fee
        cash += net_pnl
        realized += net_pnl

    funding_events = repo.list_funding_events()
    total_funding = Decimal(sum((e.amount for e in funding_events), Decimal("0")))
    # Funding adjusts cash once per event (V1 may keep funding disabled at zero).
    cash += total_funding

    open_margin = Decimal(sum(p.margin_reserved for p in repo.get_open_positions()))
    return ReconstructedWallet(
        cash=cash,
        total_fees=fees,
        total_slippage=slippage,
        total_realized_pnl=realized,
        open_margin=open_margin,
        total_funding=total_funding,
    )


def verify_accounting_independent(
    repo: PaperTradingRepository,
    *,
    initial_cash: Decimal,
) -> list[str]:
    """Compare wallet and positions against fill-based reconstruction."""
    issues: list[str] = []
    wallet = repo.get_wallet()
    if wallet is None:
        return ["wallet missing"]

    reconstructed = reconstruct_wallet(repo, initial_cash=initial_cash)

    if wallet.cash != reconstructed.cash:
        issues.append(
            f"wallet cash mismatch: db={wallet.cash} reconstructed={reconstructed.cash}"
        )
    if wallet.total_fees != reconstructed.total_fees:
        issues.append(
            f"wallet fees mismatch: db={wallet.total_fees} reconstructed={reconstructed.total_fees}"
        )
    if wallet.total_slippage != reconstructed.total_slippage:
        issues.append(
            "wallet slippage mismatch: "
            f"db={wallet.total_slippage} reconstructed={reconstructed.total_slippage}"
        )
    if wallet.total_realized_pnl != reconstructed.total_realized_pnl:
        issues.append(
            "wallet realized_pnl mismatch: "
            f"db={wallet.total_realized_pnl} reconstructed={reconstructed.total_realized_pnl}"
        )
    if wallet.total_funding != reconstructed.total_funding:
        issues.append(
            "wallet funding mismatch: "
            f"db={wallet.total_funding} reconstructed={reconstructed.total_funding}"
        )
    if wallet.total_funding != 0 and reconstructed.total_funding == 0:
        issues.append(
            "wallet total_funding nonzero without funding events: "
            f"db={wallet.total_funding}"
        )

    funding_keys: dict[str, int] = {}
    for event in repo.list_funding_events():
        key = event.deterministic_key
        funding_keys[key] = funding_keys.get(key, 0) + 1
    for key, count in funding_keys.items():
        if count > 1:
            issues.append(f"duplicate funding event key {key}")

    exit_fills_by_position: dict[str, int] = {}
    for fill in repo.list_all_fills():
        if fill.fill_kind != PaperFillKind.EXIT:
            continue
        if fill.position_id is None:
            issues.append(f"EXIT fill {fill.fill_id} missing position_id")
            continue
        key = str(fill.position_id)
        exit_fills_by_position[key] = exit_fills_by_position.get(key, 0) + 1

    for position_id, count in exit_fills_by_position.items():
        if count > 1:
            issues.append(f"duplicate EXIT fill for position {position_id}")

    positions = repo.list_positions(limit=10_000)
    for position in positions:
        if position.status == PaperPositionStatus.CLOSED:
            if position.margin_reserved != 0:
                issues.append(f"closed position {position.symbol} still reserves margin")
            if position.quantity <= 0:
                issues.append(f"closed position {position.symbol} has non-positive quantity")
            exit_count = exit_fills_by_position.get(str(position.position_id), 0)
            if exit_count == 0:
                issues.append(
                    f"closed position {position.position_id} missing canonical EXIT fill"
                )
            expected_realized = position.realized_pnl
            exit_fill = next(
                (
                    f
                    for f in repo.list_all_fills()
                    if f.fill_kind == PaperFillKind.EXIT
                    and f.position_id == position.position_id
                ),
                None,
            )
            if exit_fill is not None:
                gross = (exit_fill.fill_price - position.average_entry_price) * exit_fill.quantity
                net = gross - exit_fill.fee
                if expected_realized != net:
                    issues.append(
                        f"position {position.position_id} realized_pnl mismatch: "
                        f"db={expected_realized} from_exit_fill={net}"
                    )
        elif position.margin_reserved <= 0:
            issues.append(f"open position {position.symbol} has no margin reserved")

    return issues
