"""Unit tests for src/tax_engine.py — compute_lot_sale() and net_tax()."""
import pytest
from datetime import date
from src.tax_engine import compute_lot_sale, net_tax, EventType, LotSaleResult, TAX_RATE


# ── helpers ───────────────────────────────────────────────────────────────────

def _lot(purchase_price=100.0, purchase_commission=0.0, original_qty=100.0,
         purchase_rate=3.5, symbol="AAPL"):
    from src.portfolio import Lot
    return Lot(
        account="IB001", symbol=symbol, currency="USD",
        purchase_date=date(2021, 1, 1),
        original_qty=original_qty,
        remaining_qty=original_qty,
        purchase_price=purchase_price,
        purchase_commission=purchase_commission,
        purchase_rate=purchase_rate,
    )


def _loss_result(taxable=-5000.0):
    return LotSaleResult(
        symbol="X", purchase_date=date(2021, 1, 1), currency="USD",
        qty_sold=10.0, proceeds_nis=1000.0,
        result_a_nis=-taxable, result_b_nis=-taxable,
        taxable_nis=taxable, event_type=EventType.LOSS, gross_tax_nis=0.0,
    )


def _gain_result(taxable=10000.0):
    return LotSaleResult(
        symbol="Y", purchase_date=date(2021, 1, 1), currency="USD",
        qty_sold=10.0, proceeds_nis=20000.0,
        result_a_nis=taxable, result_b_nis=taxable,
        taxable_nis=taxable, event_type=EventType.GAIN,
        gross_tax_nis=taxable * TAX_RATE,
    )


def _zero_result():
    return LotSaleResult(
        symbol="Z", purchase_date=date(2021, 1, 1), currency="USD",
        qty_sold=5.0, proceeds_nis=5000.0,
        result_a_nis=100.0, result_b_nis=-100.0,
        taxable_nis=0.0, event_type=EventType.ZERO, gross_tax_nis=0.0,
    )


# ── compute_lot_sale ──────────────────────────────────────────────────────────

class TestComputeLotSale:
    def test_both_positive_gain_min_of_a_b(self):
        # purchase_rate < sale_rate → cost_b > cost_a → result_b < result_a
        lot = _lot(purchase_price=80.0, purchase_rate=3.0)
        result = compute_lot_sale(lot, qty_sold=10.0, sale_price_foreign=100.0,
                                  sale_rate=4.0, sale_commission_nis=0.0)
        assert result.event_type == EventType.GAIN
        assert result.taxable_nis == pytest.approx(min(result.result_a_nis, result.result_b_nis))
        assert result.result_a_nis > 0
        assert result.result_b_nis > 0

    def test_both_negative_loss_max_of_a_b(self):
        # sell at a big loss
        lot = _lot(purchase_price=200.0, purchase_rate=3.7)
        result = compute_lot_sale(lot, qty_sold=10.0, sale_price_foreign=50.0,
                                  sale_rate=3.7, sale_commission_nis=0.0)
        assert result.event_type == EventType.LOSS
        assert result.taxable_nis == pytest.approx(max(result.result_a_nis, result.result_b_nis))
        assert result.result_a_nis < 0
        assert result.result_b_nis < 0

    def test_opposite_signs_zero_event(self):
        # purchase_rate high, sale_rate low → result_a negative, result_b positive
        lot = _lot(purchase_price=100.0, purchase_rate=5.0)
        result = compute_lot_sale(lot, qty_sold=10.0, sale_price_foreign=110.0,
                                  sale_rate=3.0, sale_commission_nis=0.0)
        assert result.event_type == EventType.ZERO
        assert result.taxable_nis == pytest.approx(0.0)

    def test_proceeds_formula(self):
        lot = _lot()
        qty, price, rate, comm = 50.0, 120.0, 3.7, 10.0
        result = compute_lot_sale(lot, qty_sold=qty, sale_price_foreign=price,
                                  sale_rate=rate, sale_commission_nis=comm)
        expected = qty * price * rate - comm
        assert result.proceeds_nis == pytest.approx(expected)

    def test_cost_a_uses_sale_rate(self):
        lot = _lot(purchase_price=80.0, purchase_commission=20.0, original_qty=100.0,
                   purchase_rate=3.0)
        sale_rate = 4.0
        result = compute_lot_sale(lot, qty_sold=100.0, sale_price_foreign=100.0,
                                  sale_rate=sale_rate, sale_commission_nis=0.0)
        cost_per_share = 80.0 + 20.0 / 100.0  # = 80.2
        expected_cost_a = 100.0 * cost_per_share * sale_rate
        assert result.proceeds_nis - result.result_a_nis == pytest.approx(expected_cost_a)

    def test_cost_b_uses_purchase_rate(self):
        lot = _lot(purchase_price=80.0, purchase_commission=20.0, original_qty=100.0,
                   purchase_rate=3.2)
        result = compute_lot_sale(lot, qty_sold=100.0, sale_price_foreign=100.0,
                                  sale_rate=4.0, sale_commission_nis=0.0)
        cost_per_share = 80.0 + 20.0 / 100.0
        expected_cost_b = 100.0 * cost_per_share * 3.2
        assert result.proceeds_nis - result.result_b_nis == pytest.approx(expected_cost_b)

    def test_gross_tax_25pct_on_gain(self):
        lot = _lot(purchase_price=50.0, purchase_rate=3.5)
        result = compute_lot_sale(lot, qty_sold=10.0, sale_price_foreign=200.0,
                                  sale_rate=3.5, sale_commission_nis=0.0)
        assert result.event_type == EventType.GAIN
        assert result.gross_tax_nis == pytest.approx(result.taxable_nis * 0.25)

    def test_gross_tax_zero_on_loss(self):
        lot = _lot(purchase_price=300.0, purchase_rate=3.7)
        result = compute_lot_sale(lot, qty_sold=10.0, sale_price_foreign=50.0,
                                  sale_rate=3.7, sale_commission_nis=0.0)
        assert result.event_type == EventType.LOSS
        assert result.gross_tax_nis == pytest.approx(0.0)

    def test_zero_commission_no_effect_on_proceeds(self):
        lot = _lot()
        r_no_comm = compute_lot_sale(lot, 10.0, 100.0, 3.5, sale_commission_nis=0.0)
        r_zero = compute_lot_sale(lot, 10.0, 100.0, 3.5, sale_commission_nis=0.0)
        assert r_no_comm.proceeds_nis == pytest.approx(r_zero.proceeds_nis)


# ── net_tax ───────────────────────────────────────────────────────────────────

class TestNetTax:
    def test_gains_only_no_carryforward(self):
        results = [_gain_result(10000.0)]
        assert net_tax(results, 0.0) == pytest.approx(10000.0 * 0.25)

    def test_losses_fully_offset_gains(self):
        results = [_gain_result(5000.0), _loss_result(-5000.0)]
        assert net_tax(results, 0.0) == pytest.approx(0.0)

    def test_losses_partially_offset_gains(self):
        results = [_gain_result(10000.0), _loss_result(-3000.0)]
        assert net_tax(results, 0.0) == pytest.approx(7000.0 * 0.25)

    def test_carryforward_reduces_taxable(self):
        results = [_gain_result(10000.0)]
        assert net_tax(results, carryforward_loss_nis=4000.0) == pytest.approx(6000.0 * 0.25)

    def test_carryforward_larger_than_gain_tax_is_zero(self):
        results = [_gain_result(5000.0)]
        assert net_tax(results, carryforward_loss_nis=10000.0) == pytest.approx(0.0)

    def test_ytd_gains_added_to_proposed_gains(self):
        results = [_gain_result(5000.0)]
        tax = net_tax(results, 0.0, ytd_gains_nis=3000.0)
        assert tax == pytest.approx(8000.0 * 0.25)

    def test_ytd_losses_added_to_proposed_losses(self):
        results = [_gain_result(10000.0)]
        tax = net_tax(results, 0.0, ytd_losses_nis=4000.0)
        assert tax == pytest.approx(6000.0 * 0.25)

    def test_zero_event_lots_not_counted(self):
        results = [_zero_result(), _gain_result(8000.0)]
        assert net_tax(results, 0.0) == pytest.approx(8000.0 * 0.25)
