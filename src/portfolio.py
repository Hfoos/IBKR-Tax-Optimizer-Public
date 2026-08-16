"""
Reconstructs the FIFO lot inventory from the full transaction history.

Each BUY creates a new Lot. Each SELL consumes Lots from the front of the queue
(FIFO), which is mandatory under Israeli tax law.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date

from .parser import Transaction
from .exchange_rates import get_rate


@dataclass
class Lot:
    account: str             # IBKR account ID (e.g. U1234567)
    symbol: str
    currency: str           # USD, GBP, or EUR
    purchase_date: date
    original_qty: float     # shares at time of purchase (for commission proration)
    remaining_qty: float    # shares still held
    purchase_price: float   # per share in original currency
    purchase_commission: float  # total commission for the full original lot
    purchase_rate: float    # NIS per 1 unit of foreign currency on purchase date
    is_transfer: bool = False   # True when lot arrived via account transfer

    @property
    def cost_per_share_foreign(self) -> float:
        return self.purchase_price + self.purchase_commission / self.original_qty

    @property
    def cost_per_share_nis(self) -> float:
        return self.cost_per_share_foreign * self.purchase_rate


# (account, symbol) → FIFO deque of Lots; FIFO is per account per security
Portfolio = dict[tuple[str, str], deque[Lot]]


def build_portfolio(transactions: list[Transaction]) -> Portfolio:
    """Process all transactions chronologically and return current open lots."""
    portfolio: dict[tuple[str, str], deque] = defaultdict(deque)

    for txn in transactions:
        key = (txn.account, txn.symbol)
        if txn.quantity > 0:
            _handle_buy(portfolio, key, txn)
        else:
            _handle_sell(portfolio, key, txn)

    return {key: q for key, q in portfolio.items() if q}


def _handle_buy(portfolio: dict, key: tuple[str, str], txn: Transaction) -> None:
    rate = get_rate(txn.currency, txn.date)
    lot = Lot(
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
    )
    portfolio[key].append(lot)


def _handle_sell(portfolio: dict, key: tuple[str, str], txn: Transaction) -> None:
    qty_to_sell = abs(txn.quantity)
    queue = portfolio.get(key)
    if not queue:
        return

    while qty_to_sell > 1e-9 and queue:
        lot = queue[0]
        if lot.remaining_qty <= qty_to_sell + 1e-9:
            qty_to_sell -= lot.remaining_qty
            queue.popleft()
        else:
            lot.remaining_qty -= qty_to_sell
            qty_to_sell = 0
