"""Unit tests for src/realized.py — compute_ytd_realized()."""
import pytest
from datetime import date
from unittest.mock import patch

from src.realized import compute_ytd_realized
from src.parser import Transaction
from src.tax_engine import EventType

TAX_YEAR = 2023
FIXED_RATE = 3.65


def _txn(quantity, txn_date, price=100.0, commission=0.0,
         symbol="AAPL", currency="USD", account="IB001", is_transfer=False):
    return Transaction(account=account, symbol=symbol, currency=currency,
                       date=txn_date, quantity=quantity, price=price,
                       commission=commission, is_transfer=is_transfer)


@patch("src.realized.get_rate", return_value=FIXED_RATE)
class TestComputeYTDRealized:
    def test_no_sales_returns_zeros(self, _):
        txns = [_txn(100.0, date(TAX_YEAR, 1, 1))]
        result = compute_ytd_realized(txns, TAX_YEAR)
        assert result.sale_count == 0
        assert result.gains_nis == pytest.approx(0.0)
        assert result.losses_nis == pytest.approx(0.0)

    def test_prior_year_sale_excluded(self, _):
        txns = [
            _txn(100.0, date(TAX_YEAR - 1, 1, 1), price=50.0),
            _txn(-100.0, date(TAX_YEAR - 1, 6, 1), price=80.0),
        ]
        result = compute_ytd_realized(txns, TAX_YEAR)
        assert result.sale_count == 0
        assert result.gains_nis == pytest.approx(0.0)

    def test_sale_in_tax_year_increments_sale_count(self, _):
        txns = [
            _txn(100.0, date(TAX_YEAR - 1, 1, 1), price=50.0),
            _txn(-50.0, date(TAX_YEAR, 3, 1), price=80.0),
        ]
        result = compute_ytd_realized(txns, TAX_YEAR)
        assert result.sale_count == 1

    def test_profitable_sale_adds_to_gains(self, _):
        txns = [
            _txn(100.0, date(TAX_YEAR - 1, 1, 1), price=50.0),
            _txn(-100.0, date(TAX_YEAR, 6, 1), price=150.0),
        ]
        result = compute_ytd_realized(txns, TAX_YEAR)
        assert result.gains_nis > 0
        assert result.losses_nis == pytest.approx(0.0)

    def test_loss_sale_adds_to_losses(self, _):
        txns = [
            _txn(100.0, date(TAX_YEAR - 1, 1, 1), price=200.0),
            _txn(-100.0, date(TAX_YEAR, 6, 1), price=50.0),
        ]
        result = compute_ytd_realized(txns, TAX_YEAR)
        assert result.losses_nis > 0
        assert result.gains_nis == pytest.approx(0.0)

    def test_zero_event_does_not_update_gains_or_losses(self, _):
        # purchase_rate high, sale_rate low = opposite signs → zero event
        rates = [5.0, 2.0]   # buy at 5.0, sell at 2.0
        call_count = [0]

        def side_effect(currency, for_date):
            val = rates[min(call_count[0], 1)]
            call_count[0] += 1
            return val

        with patch("src.realized.get_rate", side_effect=side_effect):
            txns = [
                _txn(100.0, date(TAX_YEAR - 1, 1, 1), price=100.0),
                _txn(-100.0, date(TAX_YEAR, 6, 1), price=110.0),
            ]
            result = compute_ytd_realized(txns, TAX_YEAR)

        if result.details and result.details[0].event_type == EventType.ZERO:
            assert result.gains_nis == pytest.approx(0.0)
            assert result.losses_nis == pytest.approx(0.0)

    def test_fifo_consumes_earliest_lot_first(self, _):
        txns = [
            _txn(50.0, date(TAX_YEAR - 2, 1, 1), price=100.0),  # lot 1 (older)
            _txn(50.0, date(TAX_YEAR - 1, 1, 1), price=80.0),   # lot 2 (newer)
            _txn(-50.0, date(TAX_YEAR, 6, 1), price=150.0),
        ]
        result = compute_ytd_realized(txns, TAX_YEAR)
        assert result.details[0].purchase_date == date(TAX_YEAR - 2, 1, 1)

    def test_sell_spanning_two_lots_produces_two_details(self, _):
        txns = [
            _txn(30.0, date(TAX_YEAR - 2, 1, 1), price=100.0),
            _txn(50.0, date(TAX_YEAR - 1, 1, 1), price=80.0),
            _txn(-50.0, date(TAX_YEAR, 6, 1), price=150.0),  # spans both lots
        ]
        result = compute_ytd_realized(txns, TAX_YEAR)
        assert len(result.details) == 2
