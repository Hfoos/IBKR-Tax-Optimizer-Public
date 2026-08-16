"""
Computes already-realized capital gains and losses from the full transaction
history for a given tax year.

Replays transactions chronologically with FIFO lot matching and applies the
same three-step formula as the optimizer, so the YTD baseline is on identical
footing to the proposed sales.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date

from .parser import Transaction
from .portfolio import Lot
from .tax_engine import EventType, compute_lot_sale
from .exchange_rates import get_rate


@dataclass
class YTDSaleDetail:
    sale_date: date
    account: str
    symbol: str
    currency: str
    purchase_date: date   # lot's original purchase date
    qty_sold: float
    proceeds_nis: float
    taxable_nis: float    # positive = gain, negative = loss, 0 = zero event
    event_type: EventType


@dataclass
class YTDRealized:
    gains_nis: float
    losses_nis: float
    sale_count: int                        # number of sell transactions in the tax year
    details: list[YTDSaleDetail] = field(default_factory=list)


def compute_ytd_realized(transactions: list[Transaction], tax_year: int) -> YTDRealized:
    """
    Replay the full transaction history and compute gains/losses for every sell
    executed in tax_year.  Uses FIFO lot matching and the three-step formula,
    consistent with the optimizer.
    """
    inventory: dict[tuple[str, str], deque[Lot]] = defaultdict(deque)
    gains_nis = 0.0
    losses_nis = 0.0
    sale_count = 0
    details: list[YTDSaleDetail] = []

    for txn in transactions:
        key = (txn.account, txn.symbol)

        if txn.quantity > 0:
            rate = get_rate(txn.currency, txn.date)
            inventory[key].append(Lot(
                account=txn.account,
                symbol=txn.symbol,
                currency=txn.currency,
                purchase_date=txn.date,
                original_qty=txn.quantity,
                remaining_qty=txn.quantity,
                purchase_price=txn.price,
                purchase_commission=txn.commission,
                purchase_rate=rate,
                is_transfer=txn.is_transfer,
            ))

        else:
            total_qty = abs(txn.quantity)
            qty_remaining = total_qty
            queue = inventory.get(key)
            if not queue:
                continue

            in_tax_year = txn.date.year == tax_year
            if in_tax_year:
                sale_rate = get_rate(txn.currency, txn.date)
                sale_count += 1

            while qty_remaining > 1e-9 and queue:
                lot = queue[0]
                qty_from_lot = min(lot.remaining_qty, qty_remaining)

                if in_tax_year:
                    # Apportion sell commission to this lot's share of the total quantity
                    commission_share_nis = (
                        txn.commission * (qty_from_lot / total_qty) * sale_rate
                    )
                    result = compute_lot_sale(
                        lot=lot,
                        qty_sold=qty_from_lot,
                        sale_price_foreign=txn.price,
                        sale_rate=sale_rate,
                        sale_commission_nis=commission_share_nis,
                    )
                    if result.event_type == EventType.GAIN:
                        gains_nis += result.taxable_nis
                    elif result.event_type == EventType.LOSS:
                        losses_nis += abs(result.taxable_nis)
                    details.append(YTDSaleDetail(
                        sale_date=txn.date,
                        account=txn.account,
                        symbol=txn.symbol,
                        currency=txn.currency,
                        purchase_date=lot.purchase_date,
                        qty_sold=qty_from_lot,
                        proceeds_nis=result.proceeds_nis,
                        taxable_nis=result.taxable_nis,
                        event_type=result.event_type,
                    ))

                if lot.remaining_qty <= qty_remaining + 1e-9:
                    qty_remaining -= lot.remaining_qty
                    queue.popleft()
                else:
                    lot.remaining_qty -= qty_remaining
                    qty_remaining = 0

    return YTDRealized(gains_nis=gains_nis, losses_nis=losses_nis, sale_count=sale_count, details=details)
