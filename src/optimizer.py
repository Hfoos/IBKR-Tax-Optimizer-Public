"""
Greedy optimizer: selects which positions (and how many shares) to sell
to reach the target NIS proceeds while minimizing tax.

Optimization lever: WHICH securities to sell and HOW MANY shares.
Within each security, lots are always consumed FIFO — this is fixed by Israeli law.

Algorithm:
  1. For each security, the "accessible tranche" is its next FIFO lot.
  2. Each tranche is scored by tax efficiency using the three-step formula.
  3. Priority order: LOSS tranches first → ZERO EVENT → GAIN (lowest rate last).
  4. Greedily consume the best accessible tranche (fully or partially).
  5. After a lot is fully consumed, the next lot of that security becomes accessible.
  6. Repeat until cumulative proceeds >= target.
  7. Compute net tax accounting for cross-position offsets and carryforward.
"""

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import date

from .portfolio import Lot, Portfolio
from .tax_engine import (
    EventType,
    LotSaleResult,
    TAX_RATE,
    compute_lot_sale,
    net_tax,
)
from .exchange_rates import get_rate


@dataclass
class SellRecommendation:
    account: str
    symbol: str
    currency: str
    purchase_date: date
    qty_to_sell: float
    current_price: float        # in original currency
    proceeds_nis: float
    result_a_nis: float
    result_b_nis: float
    taxable_nis: float
    event_type: EventType
    gross_tax_nis: float        # before cross-position netting
    purchase_price: float = 0.0
    purchase_commission: float = 0.0
    original_qty: float = 0.0
    purchase_rate: float = 0.0
    sale_rate: float = 0.0


@dataclass
class OptimizationResult:
    recommendations: list[SellRecommendation]
    total_proceeds_nis: float
    total_gains_nis: float              # from proposed sales only
    total_losses_nis: float             # from proposed sales only
    net_tax_nis: float
    remaining_carryforward_nis: float   # unused carryforward after offsetting
    ytd_gains_nis: float = 0.0          # already realized this tax year
    ytd_losses_nis: float = 0.0         # already realized this tax year


def optimize(
    portfolio: Portfolio,
    current_prices: dict[str, float],   # symbol → price in original currency
    current_rates: dict[str, float],    # currency → NIS rate (e.g. "USD" → 3.65)
    target_nis: float,
    carryforward_loss_nis: float = 0.0,
    ytd_gains_nis: float = 0.0,
    ytd_losses_nis: float = 0.0,
) -> OptimizationResult:
    # Work on a deep copy so we don't mutate the caller's portfolio
    working_portfolio: dict[tuple[str, str], deque[Lot]] = {
        key: deque(deepcopy(list(q))) for key, q in portfolio.items()
    }

    recommendations: list[SellRecommendation] = []
    lot_results: list[LotSaleResult] = []
    total_proceeds = 0.0

    while total_proceeds < target_nis:
        candidates = _build_candidates(
            working_portfolio, current_prices, current_rates, target_nis, total_proceeds
        )
        if not candidates:
            break  # No more lots available

        best = _pick_best(candidates)
        account = best["account"]
        symbol = best["symbol"]
        key = (account, symbol)
        lot: Lot = working_portfolio[key][0]
        rate = current_rates.get(lot.currency, current_rates.get("USD", 1.0))
        price = current_prices[symbol]

        # How many shares to sell from this lot
        needed_nis = target_nis - total_proceeds
        max_proceeds_this_lot = lot.remaining_qty * price * rate
        if max_proceeds_this_lot <= needed_nis:
            qty = lot.remaining_qty
        else:
            # Partial sell: only as many shares as needed to hit target
            qty = needed_nis / (price * rate)
            qty = min(qty, lot.remaining_qty)

        # Commission is proportional to shares sold (we allocate 0 sale commission
        # here; the user's actual commission at sale time is unknowable in advance,
        # so we omit it from the projection — it's typically < 0.1% of proceeds)
        result = compute_lot_sale(
            lot=lot,
            qty_sold=qty,
            sale_price_foreign=price,
            sale_rate=rate,
            sale_commission_nis=0.0,
        )

        recommendations.append(SellRecommendation(
            account=account,
            symbol=symbol,
            currency=lot.currency,
            purchase_date=lot.purchase_date,
            qty_to_sell=round(qty, 6),
            current_price=price,
            proceeds_nis=result.proceeds_nis,
            result_a_nis=result.result_a_nis,
            result_b_nis=result.result_b_nis,
            taxable_nis=result.taxable_nis,
            event_type=result.event_type,
            gross_tax_nis=result.gross_tax_nis,
            purchase_price=lot.purchase_price,
            purchase_commission=lot.purchase_commission,
            original_qty=lot.original_qty,
            purchase_rate=lot.purchase_rate,
            sale_rate=rate,
        ))
        lot_results.append(result)
        total_proceeds += result.proceeds_nis

        # Consume the lot
        if lot.remaining_qty - qty < 1e-6:
            working_portfolio[key].popleft()
            if not working_portfolio[key]:
                del working_portfolio[key]
        else:
            lot.remaining_qty -= qty

    tax_nis = net_tax(lot_results, carryforward_loss_nis, ytd_gains_nis, ytd_losses_nis)
    total_gains = sum(r.taxable_nis for r in lot_results if r.event_type == EventType.GAIN)
    total_losses = sum(abs(r.taxable_nis) for r in lot_results if r.event_type == EventType.LOSS)
    all_gains = ytd_gains_nis + total_gains
    all_losses = ytd_losses_nis + total_losses
    remaining_cf = max(0.0, abs(carryforward_loss_nis) - max(0.0, all_gains - all_losses))

    return OptimizationResult(
        recommendations=recommendations,
        total_proceeds_nis=total_proceeds,
        total_gains_nis=total_gains,
        total_losses_nis=total_losses,
        net_tax_nis=tax_nis,
        remaining_carryforward_nis=remaining_cf,
        ytd_gains_nis=ytd_gains_nis,
        ytd_losses_nis=ytd_losses_nis,
    )


def compute_manual_sale(
    selections: dict[tuple[str, str], float],
    portfolio: Portfolio,
    current_prices: dict[str, float],
    current_rates: dict[str, float],
    carryforward_loss_nis: float = 0.0,
    ytd_gains_nis: float = 0.0,
    ytd_losses_nis: float = 0.0,
) -> OptimizationResult:
    """Compute tax for a user-specified set of (account, symbol) → qty_to_sell.

    Lot consumption is FIFO within each security, identical to optimize().
    """
    working_portfolio: dict[tuple[str, str], deque[Lot]] = {
        key: deque(deepcopy(list(q))) for key, q in portfolio.items()
    }

    recommendations: list[SellRecommendation] = []
    lot_results: list[LotSaleResult] = []
    total_proceeds = 0.0

    for key, qty_requested in selections.items():
        account, symbol = key
        queue = working_portfolio.get(key)
        if not queue or symbol not in current_prices:
            continue

        price = current_prices[symbol]
        qty_remaining = qty_requested

        while qty_remaining > 1e-9 and queue:
            lot = queue[0]
            rate = current_rates.get(lot.currency, current_rates.get("USD", 1.0))
            qty = min(lot.remaining_qty, qty_remaining)

            result = compute_lot_sale(
                lot=lot,
                qty_sold=qty,
                sale_price_foreign=price,
                sale_rate=rate,
                sale_commission_nis=0.0,
            )

            recommendations.append(SellRecommendation(
                account=account,
                symbol=symbol,
                currency=lot.currency,
                purchase_date=lot.purchase_date,
                qty_to_sell=round(qty, 6),
                current_price=price,
                proceeds_nis=result.proceeds_nis,
                result_a_nis=result.result_a_nis,
                result_b_nis=result.result_b_nis,
                taxable_nis=result.taxable_nis,
                event_type=result.event_type,
                gross_tax_nis=result.gross_tax_nis,
                purchase_price=lot.purchase_price,
                purchase_commission=lot.purchase_commission,
                original_qty=lot.original_qty,
                purchase_rate=lot.purchase_rate,
                sale_rate=rate,
            ))
            lot_results.append(result)
            total_proceeds += result.proceeds_nis
            qty_remaining -= qty

            if lot.remaining_qty - qty < 1e-6:
                queue.popleft()
            else:
                lot.remaining_qty -= qty

    tax_nis = net_tax(lot_results, carryforward_loss_nis, ytd_gains_nis, ytd_losses_nis)
    total_gains = sum(r.taxable_nis for r in lot_results if r.event_type == EventType.GAIN)
    total_losses = sum(abs(r.taxable_nis) for r in lot_results if r.event_type == EventType.LOSS)
    all_gains = ytd_gains_nis + total_gains
    all_losses = ytd_losses_nis + total_losses
    remaining_cf = max(0.0, abs(carryforward_loss_nis) - max(0.0, all_gains - all_losses))

    return OptimizationResult(
        recommendations=recommendations,
        total_proceeds_nis=total_proceeds,
        total_gains_nis=total_gains,
        total_losses_nis=total_losses,
        net_tax_nis=tax_nis,
        remaining_carryforward_nis=remaining_cf,
        ytd_gains_nis=ytd_gains_nis,
        ytd_losses_nis=ytd_losses_nis,
    )


def _build_candidates(
    portfolio: dict[tuple[str, str], deque[Lot]],
    prices: dict[str, float],
    rates: dict[str, float],
    target_nis: float,
    already_raised: float,
) -> list[dict]:
    candidates = []
    for (account, symbol), queue in portfolio.items():
        if not queue or symbol not in prices:
            continue
        lot = queue[0]
        price = prices[symbol]
        rate = rates.get(lot.currency, rates.get("USD", 1.0))
        result = compute_lot_sale(lot, lot.remaining_qty, price, rate, 0.0)
        candidates.append({
            "account": account,
            "symbol": symbol,
            "event_type": result.event_type,
            "taxable_nis": result.taxable_nis,
            "proceeds_nis": result.proceeds_nis,
            "tax_rate": (
                result.taxable_nis / result.proceeds_nis
                if result.proceeds_nis > 0 and result.event_type == EventType.GAIN
                else 0.0
            ),
        })
    return candidates


def _pick_best(candidates: list[dict]) -> dict:
    def sort_key(c: dict):
        et = c["event_type"]
        if et == EventType.LOSS:
            # Highest proceeds first (maximise free cash from loss positions)
            return (0, -c["proceeds_nis"])
        elif et == EventType.ZERO:
            return (1, -c["proceeds_nis"])
        else:
            # Lowest effective tax rate first
            return (2, c["tax_rate"])

    return sorted(candidates, key=sort_key)[0]
