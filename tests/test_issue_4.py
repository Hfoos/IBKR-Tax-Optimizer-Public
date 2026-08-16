"""Tests for lot-level explainer panel data — issue #4."""
import pytest
from datetime import date

from src.optimizer import SellRecommendation, OptimizationResult
from src.tax_engine import EventType


def _rec(
    symbol="AAPL",
    account="IB001",
    currency="USD",
    purchase_date=date(2022, 1, 1),
    qty=100.0,
    current_price=150.0,
    proceeds_nis=50000.0,
    result_a_nis=10000.0,
    result_b_nis=8000.0,
    taxable_nis=8000.0,
    event_type=EventType.GAIN,
    gross_tax_nis=2000.0,
    purchase_price=100.0,
    purchase_commission=10.0,
    original_qty=100.0,
    purchase_rate=3.5,
    sale_rate=3.7,
):
    return SellRecommendation(
        account=account,
        symbol=symbol,
        currency=currency,
        purchase_date=purchase_date,
        qty_to_sell=qty,
        current_price=current_price,
        proceeds_nis=proceeds_nis,
        result_a_nis=result_a_nis,
        result_b_nis=result_b_nis,
        taxable_nis=taxable_nis,
        event_type=event_type,
        gross_tax_nis=gross_tax_nis,
        purchase_price=purchase_price,
        purchase_commission=purchase_commission,
        original_qty=original_qty,
        purchase_rate=purchase_rate,
        sale_rate=sale_rate,
    )


# ── Field population ──────────────────────────────────────────────────────────

def test_new_fields_stored_on_recommendation():
    rec = _rec(purchase_price=80.0, purchase_commission=5.0, original_qty=50.0,
               purchase_rate=3.4, sale_rate=3.8)
    assert rec.purchase_price == pytest.approx(80.0)
    assert rec.purchase_commission == pytest.approx(5.0)
    assert rec.original_qty == pytest.approx(50.0)
    assert rec.purchase_rate == pytest.approx(3.4)
    assert rec.sale_rate == pytest.approx(3.8)


def test_cost_per_share_formula():
    """cost_per_share = purchase_price + commission / original_qty"""
    rec = _rec(purchase_price=100.0, purchase_commission=20.0, original_qty=200.0)
    cost_per_share = rec.purchase_price + rec.purchase_commission / rec.original_qty
    assert cost_per_share == pytest.approx(100.1)


# ── Proceeds arithmetic ───────────────────────────────────────────────────────

def test_proceeds_formula_consistent():
    """qty × price × sale_rate should equal proceeds_nis."""
    qty, price, sale_rate = 50.0, 200.0, 3.7
    proceeds = qty * price * sale_rate
    rec = _rec(qty=qty, current_price=price, sale_rate=sale_rate, proceeds_nis=proceeds)
    assert rec.qty_to_sell * rec.current_price * rec.sale_rate == pytest.approx(rec.proceeds_nis)


# ── Tax rule selection ────────────────────────────────────────────────────────

def test_both_positive_taxable_is_min():
    rec = _rec(result_a_nis=5000.0, result_b_nis=3000.0,
               taxable_nis=3000.0, event_type=EventType.GAIN)
    assert rec.taxable_nis == pytest.approx(min(rec.result_a_nis, rec.result_b_nis))


def test_both_negative_taxable_is_max():
    rec = _rec(result_a_nis=-4000.0, result_b_nis=-2000.0,
               taxable_nis=-2000.0, event_type=EventType.LOSS)
    assert rec.taxable_nis == pytest.approx(max(rec.result_a_nis, rec.result_b_nis))


def test_opposite_signs_is_zero_event():
    rec = _rec(result_a_nis=3000.0, result_b_nis=-1000.0,
               taxable_nis=0.0, event_type=EventType.ZERO)
    assert rec.taxable_nis == pytest.approx(0.0)
    assert rec.event_type == EventType.ZERO


def test_gross_tax_is_25_pct_of_taxable_gain():
    taxable = 8000.0
    rec = _rec(taxable_nis=taxable, gross_tax_nis=taxable * 0.25, event_type=EventType.GAIN)
    assert rec.gross_tax_nis == pytest.approx(rec.taxable_nis * 0.25)


# ── Cost A / Cost B consistency ───────────────────────────────────────────────

def test_result_a_equals_proceeds_minus_cost_a():
    """result_a_nis = proceeds_nis - cost_a_nis"""
    rec = _rec(proceeds_nis=50000.0, result_a_nis=10000.0)
    cost_a = rec.proceeds_nis - rec.result_a_nis
    assert cost_a == pytest.approx(40000.0)


def test_result_b_equals_proceeds_minus_cost_b():
    rec = _rec(proceeds_nis=50000.0, result_b_nis=8000.0)
    cost_b = rec.proceeds_nis - rec.result_b_nis
    assert cost_b == pytest.approx(42000.0)


# ── Optimizer populates new fields ────────────────────────────────────────────

def test_optimizer_populates_explainer_fields():
    """End-to-end: optimize() must fill purchase_price, purchase_rate, sale_rate, etc."""
    from collections import deque
    from src.optimizer import optimize
    from src.portfolio import Lot

    lot = Lot(
        account="IB001",
        symbol="MSFT",
        currency="USD",
        purchase_date=date(2021, 6, 1),
        original_qty=10.0,
        remaining_qty=10.0,
        purchase_price=250.0,
        purchase_commission=2.0,
        purchase_rate=3.3,
    )
    portfolio = {("IB001", "MSFT"): deque([lot])}
    current_prices = {"MSFT": 300.0}
    current_rates = {"USD": 3.7}

    result = optimize(portfolio, current_prices, current_rates, target_nis=5000.0)

    assert result.recommendations, "Expected at least one recommendation"
    rec = result.recommendations[0]
    assert rec.purchase_price == pytest.approx(250.0)
    assert rec.purchase_commission == pytest.approx(2.0)
    assert rec.original_qty == pytest.approx(10.0)
    assert rec.purchase_rate == pytest.approx(3.3)
    assert rec.sale_rate == pytest.approx(3.7)
