"""Unit tests for src/portfolio.py — Lot properties and build_portfolio()."""
import pytest
from collections import deque
from datetime import date
from unittest.mock import patch

from src.portfolio import Lot, build_portfolio
from src.parser import Transaction


FIXED_RATE = 3.65


def _txn(quantity, date_=date(2022, 1, 1), price=100.0, commission=0.0,
         symbol="AAPL", currency="USD", account="IB001", is_transfer=False):
    return Transaction(account=account, symbol=symbol, currency=currency,
                       date=date_, quantity=quantity, price=price,
                       commission=commission, is_transfer=is_transfer)


# ── Lot properties ────────────────────────────────────────────────────────────

class TestLotProperties:
    def test_cost_per_share_includes_commission(self):
        lot = Lot("IB001", "AAPL", "USD", date(2022, 1, 1),
                  original_qty=100.0, remaining_qty=100.0,
                  purchase_price=80.0, purchase_commission=20.0, purchase_rate=3.5)
        assert lot.cost_per_share_foreign == pytest.approx(80.0 + 20.0 / 100.0)

    def test_cost_per_share_zero_commission(self):
        lot = Lot("IB001", "AAPL", "USD", date(2022, 1, 1),
                  original_qty=50.0, remaining_qty=50.0,
                  purchase_price=120.0, purchase_commission=0.0, purchase_rate=3.5)
        assert lot.cost_per_share_foreign == pytest.approx(120.0)


# ── build_portfolio ───────────────────────────────────────────────────────────

@patch("src.portfolio.get_rate", return_value=FIXED_RATE)
class TestBuildPortfolio:
    def test_single_buy_creates_one_lot(self, _):
        txns = [_txn(100.0, price=50.0, commission=5.0)]
        portfolio = build_portfolio(txns)
        assert ("IB001", "AAPL") in portfolio
        lot = portfolio[("IB001", "AAPL")][0]
        assert lot.original_qty == pytest.approx(100.0)
        assert lot.purchase_price == pytest.approx(50.0)
        assert lot.purchase_commission == pytest.approx(5.0)
        assert lot.purchase_rate == pytest.approx(FIXED_RATE)

    def test_buy_then_full_sell_removes_position(self, _):
        txns = [_txn(100.0), _txn(-100.0, date_=date(2022, 6, 1))]
        portfolio = build_portfolio(txns)
        assert ("IB001", "AAPL") not in portfolio

    def test_buy_then_partial_sell_reduces_qty(self, _):
        txns = [_txn(100.0), _txn(-40.0, date_=date(2022, 6, 1))]
        portfolio = build_portfolio(txns)
        lot = portfolio[("IB001", "AAPL")][0]
        assert lot.remaining_qty == pytest.approx(60.0)

    def test_two_buys_full_sell_of_first_fifo(self, _):
        txns = [
            _txn(50.0, date_=date(2021, 1, 1)),
            _txn(80.0, date_=date(2022, 1, 1)),
            _txn(-50.0, date_=date(2023, 1, 1)),
        ]
        portfolio = build_portfolio(txns)
        queue = portfolio[("IB001", "AAPL")]
        assert len(queue) == 1
        assert queue[0].original_qty == pytest.approx(80.0)

    def test_two_buys_partial_sell_of_first_fifo(self, _):
        txns = [
            _txn(50.0, date_=date(2021, 1, 1)),
            _txn(80.0, date_=date(2022, 1, 1)),
            _txn(-30.0, date_=date(2023, 1, 1)),
        ]
        portfolio = build_portfolio(txns)
        queue = portfolio[("IB001", "AAPL")]
        assert len(queue) == 2
        assert queue[0].remaining_qty == pytest.approx(20.0)
        assert queue[1].remaining_qty == pytest.approx(80.0)

    def test_two_symbols_tracked_independently(self, _):
        txns = [
            _txn(100.0, symbol="AAPL"),
            _txn(50.0, symbol="MSFT"),
        ]
        portfolio = build_portfolio(txns)
        assert ("IB001", "AAPL") in portfolio
        assert ("IB001", "MSFT") in portfolio

    def test_two_accounts_tracked_independently(self, _):
        txns = [
            _txn(100.0, account="IB001"),
            _txn(80.0, account="IB002"),
        ]
        portfolio = build_portfolio(txns)
        assert ("IB001", "AAPL") in portfolio
        assert ("IB002", "AAPL") in portfolio
        assert portfolio[("IB001", "AAPL")][0].original_qty == pytest.approx(100.0)
        assert portfolio[("IB002", "AAPL")][0].original_qty == pytest.approx(80.0)

    def test_transfer_in_sets_is_transfer_flag(self, _):
        txns = [_txn(100.0, is_transfer=True)]
        portfolio = build_portfolio(txns)
        lot = portfolio[("IB001", "AAPL")][0]
        assert lot.is_transfer is True
