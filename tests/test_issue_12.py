"""Tests for compute_manual_sale() and build_selections() — issue #12."""
import pytest
from collections import deque
from copy import deepcopy
from datetime import date

from src.optimizer import compute_manual_sale, OptimizationResult
from src.portfolio import Lot
from src.tax_engine import EventType
from app import build_selections


PRICES = {"AAPL": 150.0, "MSFT": 300.0}
RATES = {"USD": 3.7}


def _lot(symbol="AAPL", account="IB001", purchase_price=100.0,
         purchase_rate=3.5, qty=100.0, purchase_date=date(2021, 1, 1)):
    return Lot(
        account=account, symbol=symbol, currency="USD",
        purchase_date=purchase_date,
        original_qty=qty, remaining_qty=qty,
        purchase_price=purchase_price, purchase_commission=0.0,
        purchase_rate=purchase_rate,
    )


def _portfolio(*lots):
    result = {}
    for lot in lots:
        key = (lot.account, lot.symbol)
        if key not in result:
            result[key] = deque()
        result[key].append(lot)
    return result


# ── basic correctness ─────────────────────────────────────────────────────────

def test_returns_optimization_result():
    portfolio = _portfolio(_lot(qty=100.0))
    result = compute_manual_sale({("IB001", "AAPL"): 50.0}, portfolio, PRICES, RATES)
    assert isinstance(result, OptimizationResult)


def test_empty_selections_returns_empty_result():
    portfolio = _portfolio(_lot())
    result = compute_manual_sale({}, portfolio, PRICES, RATES)
    assert result.recommendations == []
    assert result.total_proceeds_nis == pytest.approx(0.0)
    assert result.net_tax_nis == pytest.approx(0.0)


def test_partial_sell_single_lot():
    portfolio = _portfolio(_lot(qty=100.0, purchase_price=100.0))
    result = compute_manual_sale({("IB001", "AAPL"): 40.0}, portfolio, PRICES, RATES)
    assert len(result.recommendations) == 1
    assert result.recommendations[0].qty_to_sell == pytest.approx(40.0)


def test_full_sell_single_lot():
    portfolio = _portfolio(_lot(qty=100.0))
    result = compute_manual_sale({("IB001", "AAPL"): 100.0}, portfolio, PRICES, RATES)
    assert len(result.recommendations) == 1
    assert result.recommendations[0].qty_to_sell == pytest.approx(100.0)


def test_proceeds_formula_correct():
    portfolio = _portfolio(_lot(qty=10.0))
    result = compute_manual_sale({("IB001", "AAPL"): 10.0}, portfolio, PRICES, RATES)
    expected = 10.0 * PRICES["AAPL"] * RATES["USD"]
    assert result.total_proceeds_nis == pytest.approx(expected)


# ── FIFO consumption ──────────────────────────────────────────────────────────

def test_fifo_consumes_first_lot_before_second():
    lot1 = _lot(qty=100.0, purchase_price=50.0, purchase_date=date(2020, 1, 1))
    lot2 = _lot(qty=100.0, purchase_price=200.0, purchase_date=date(2021, 1, 1))
    portfolio = _portfolio(lot1, lot2)
    result = compute_manual_sale({("IB001", "AAPL"): 100.0}, portfolio, PRICES, RATES)
    assert len(result.recommendations) == 1
    assert result.recommendations[0].purchase_date == date(2020, 1, 1)


def test_sell_spanning_two_lots_produces_two_recommendations():
    lot1 = _lot(qty=100.0, purchase_date=date(2020, 1, 1))
    lot2 = _lot(qty=200.0, purchase_date=date(2021, 1, 1))
    portfolio = _portfolio(lot1, lot2)
    result = compute_manual_sale({("IB001", "AAPL"): 150.0}, portfolio, PRICES, RATES)
    assert len(result.recommendations) == 2
    assert result.recommendations[0].purchase_date == date(2020, 1, 1)
    assert result.recommendations[0].qty_to_sell == pytest.approx(100.0)
    assert result.recommendations[1].purchase_date == date(2021, 1, 1)
    assert result.recommendations[1].qty_to_sell == pytest.approx(50.0)


def test_portfolio_not_mutated():
    lot = _lot(qty=100.0)
    portfolio = _portfolio(lot)
    original_qty = portfolio[("IB001", "AAPL")][0].remaining_qty
    compute_manual_sale({("IB001", "AAPL"): 60.0}, portfolio, PRICES, RATES)
    assert portfolio[("IB001", "AAPL")][0].remaining_qty == pytest.approx(original_qty)


# ── multi-position ────────────────────────────────────────────────────────────

def test_multiple_positions_all_processed():
    portfolio = _portfolio(
        _lot(symbol="AAPL", qty=50.0),
        _lot(symbol="MSFT", qty=10.0),
    )
    selections = {("IB001", "AAPL"): 50.0, ("IB001", "MSFT"): 10.0}
    result = compute_manual_sale(selections, portfolio, PRICES, RATES)
    symbols = {r.symbol for r in result.recommendations}
    assert symbols == {"AAPL", "MSFT"}


def test_total_proceeds_is_sum_of_recommendations():
    portfolio = _portfolio(
        _lot(symbol="AAPL", qty=50.0),
        _lot(symbol="MSFT", qty=10.0),
    )
    selections = {("IB001", "AAPL"): 50.0, ("IB001", "MSFT"): 10.0}
    result = compute_manual_sale(selections, portfolio, PRICES, RATES)
    expected = sum(r.proceeds_nis for r in result.recommendations)
    assert result.total_proceeds_nis == pytest.approx(expected)


def test_position_not_in_portfolio_is_skipped():
    portfolio = _portfolio(_lot(symbol="AAPL", qty=100.0))
    selections = {("IB001", "AAPL"): 50.0, ("IB001", "MSFT"): 10.0}
    result = compute_manual_sale(selections, portfolio, PRICES, RATES)
    assert all(r.symbol == "AAPL" for r in result.recommendations)


# ── tax calculation ───────────────────────────────────────────────────────────

def test_gains_and_losses_summed_correctly():
    lot_gain = _lot(symbol="AAPL", purchase_price=50.0, qty=10.0)   # sell at 150 → gain
    lot_loss = _lot(symbol="MSFT", purchase_price=400.0, qty=10.0)  # sell at 300 → loss
    portfolio = _portfolio(lot_gain, lot_loss)
    selections = {("IB001", "AAPL"): 10.0, ("IB001", "MSFT"): 10.0}
    result = compute_manual_sale(selections, portfolio, PRICES, RATES)
    assert result.total_gains_nis > 0
    assert result.total_losses_nis > 0


def test_carryforward_reduces_net_tax():
    portfolio = _portfolio(_lot(purchase_price=50.0, qty=100.0))
    r_no_cf = compute_manual_sale({("IB001", "AAPL"): 10.0}, portfolio, PRICES, RATES,
                                   carryforward_loss_nis=0.0)
    r_cf = compute_manual_sale({("IB001", "AAPL"): 10.0}, portfolio, PRICES, RATES,
                                carryforward_loss_nis=10000.0)
    assert r_cf.net_tax_nis <= r_no_cf.net_tax_nis


# ── build_selections (app-level helper) ───────────────────────────────────────

def test_build_selections_accepts_list_of_dicts():
    """st.data_editor returns a list when given a list — must not call .to_dict()."""
    portfolio = _portfolio(_lot(qty=100.0))
    keys = [("IB001", "AAPL")]
    rows = [{"Account": "IB001", "Symbol": "AAPL", "Shares held": "100", "Shares to sell": 40.0}]
    result = build_selections(rows, keys, portfolio)
    assert result == {("IB001", "AAPL"): pytest.approx(40.0)}


def test_build_selections_zero_qty_excluded():
    portfolio = _portfolio(_lot(qty=100.0))
    keys = [("IB001", "AAPL")]
    rows = [{"Account": "IB001", "Symbol": "AAPL", "Shares held": "100", "Shares to sell": 0.0}]
    result = build_selections(rows, keys, portfolio)
    assert result == {}


def test_build_selections_clamps_to_held():
    portfolio = _portfolio(_lot(qty=50.0))
    keys = [("IB001", "AAPL")]
    rows = [{"Account": "IB001", "Symbol": "AAPL", "Shares held": "50", "Shares to sell": 999.0}]
    result = build_selections(rows, keys, portfolio)
    assert result[("IB001", "AAPL")] == pytest.approx(50.0)


def test_build_selections_multiple_positions():
    portfolio = _portfolio(_lot(symbol="AAPL", qty=100.0), _lot(symbol="MSFT", qty=20.0))
    keys = [("IB001", "AAPL"), ("IB001", "MSFT")]
    rows = [
        {"Account": "IB001", "Symbol": "AAPL", "Shares held": "100", "Shares to sell": 30.0},
        {"Account": "IB001", "Symbol": "MSFT", "Shares held": "20", "Shares to sell": 0.0},
    ]
    result = build_selections(rows, keys, portfolio)
    assert set(result.keys()) == {("IB001", "AAPL")}
    assert result[("IB001", "AAPL")] == pytest.approx(30.0)
