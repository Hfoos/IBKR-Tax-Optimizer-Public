"""Unit tests for src/optimizer.py — _pick_best, _build_candidates, optimize()."""
import pytest
from collections import deque
from datetime import date

from src.optimizer import optimize, _pick_best, _build_candidates
from src.portfolio import Lot
from src.tax_engine import EventType


def _lot(symbol="AAPL", account="IB001", purchase_price=100.0, purchase_rate=3.5,
         qty=100.0, currency="USD", purchase_commission=0.0,
         purchase_date=date(2021, 1, 1)):
    return Lot(
        account=account, symbol=symbol, currency=currency,
        purchase_date=purchase_date,
        original_qty=qty, remaining_qty=qty,
        purchase_price=purchase_price, purchase_commission=purchase_commission,
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


# ── _pick_best ────────────────────────────────────────────────────────────────

class TestPickBest:
    def _candidate(self, event_type, proceeds=10000.0, tax_rate=0.0, taxable=0.0):
        return {"account": "IB001", "symbol": "X", "event_type": event_type,
                "proceeds_nis": proceeds, "tax_rate": tax_rate, "taxable_nis": taxable}

    def test_loss_ranked_before_zero(self):
        candidates = [
            self._candidate(EventType.ZERO, proceeds=20000.0),
            self._candidate(EventType.LOSS, proceeds=5000.0),
        ]
        best = _pick_best(candidates)
        assert best["event_type"] == EventType.LOSS

    def test_zero_ranked_before_gain(self):
        candidates = [
            self._candidate(EventType.GAIN, proceeds=50000.0, tax_rate=0.05),
            self._candidate(EventType.ZERO, proceeds=1000.0),
        ]
        best = _pick_best(candidates)
        assert best["event_type"] == EventType.ZERO

    def test_among_losses_highest_proceeds_wins(self):
        candidates = [
            self._candidate(EventType.LOSS, proceeds=5000.0),
            self._candidate(EventType.LOSS, proceeds=15000.0),
        ]
        best = _pick_best(candidates)
        assert best["proceeds_nis"] == pytest.approx(15000.0)

    def test_among_gains_lowest_tax_rate_wins(self):
        candidates = [
            self._candidate(EventType.GAIN, proceeds=10000.0, tax_rate=0.20),
            self._candidate(EventType.GAIN, proceeds=10000.0, tax_rate=0.05),
        ]
        best = _pick_best(candidates)
        assert best["tax_rate"] == pytest.approx(0.05)


# ── _build_candidates ─────────────────────────────────────────────────────────

class TestBuildCandidates:
    def test_only_first_fifo_lot_considered(self):
        lot1 = _lot(symbol="AAPL", purchase_price=50.0)
        lot2 = _lot(symbol="AAPL", purchase_price=200.0)
        portfolio = {("IB001", "AAPL"): deque([lot1, lot2])}
        prices = {"AAPL": 100.0}
        rates = {"USD": 3.5}
        candidates = _build_candidates(portfolio, prices, rates, 100000.0, 0.0)
        assert len(candidates) == 1

    def test_symbol_without_price_excluded(self):
        lot = _lot(symbol="NOPRICE")
        portfolio = {("IB001", "NOPRICE"): deque([lot])}
        prices = {}
        rates = {"USD": 3.5}
        candidates = _build_candidates(portfolio, prices, rates, 100000.0, 0.0)
        assert len(candidates) == 0


# ── optimize ──────────────────────────────────────────────────────────────────

class TestOptimize:
    PRICES = {"AAPL": 150.0}
    RATES = {"USD": 3.7}

    def test_stops_when_target_reached(self):
        lot = _lot(purchase_price=100.0, qty=1000.0)
        result = optimize(_portfolio(lot), self.PRICES, self.RATES, target_nis=10000.0)
        assert result.total_proceeds_nis >= 10000.0

    def test_partial_lot_when_last_lot_exceeds_target(self):
        lot = _lot(purchase_price=100.0, qty=1000.0)
        target = 5000.0
        result = optimize(_portfolio(lot), self.PRICES, self.RATES, target_nis=target)
        assert len(result.recommendations) == 1
        assert result.recommendations[0].qty_to_sell < 1000.0
        assert result.total_proceeds_nis == pytest.approx(target, rel=1e-4)

    def test_total_proceeds_equals_sum_of_recommendations(self):
        lot1 = _lot(symbol="AAPL", qty=10.0)
        lot2 = _lot(symbol="MSFT", qty=10.0, purchase_price=80.0)
        prices = {"AAPL": 150.0, "MSFT": 120.0}
        result = optimize(_portfolio(lot1, lot2), prices, self.RATES, target_nis=5000.0)
        expected = sum(r.proceeds_nis for r in result.recommendations)
        assert result.total_proceeds_nis == pytest.approx(expected)

    def test_gains_losses_match_lot_results(self):
        lot = _lot(purchase_price=50.0, qty=100.0)
        result = optimize(_portfolio(lot), self.PRICES, self.RATES, target_nis=5000.0)
        for rec in result.recommendations:
            if rec.taxable_nis > 0:
                assert result.total_gains_nis >= rec.taxable_nis
            elif rec.taxable_nis < 0:
                assert result.total_losses_nis >= abs(rec.taxable_nis)

    def test_empty_portfolio_returns_empty(self):
        result = optimize({}, self.PRICES, self.RATES, target_nis=10000.0)
        assert result.recommendations == []
        assert result.total_proceeds_nis == pytest.approx(0.0)

    def test_target_met_after_first_lot_no_more_consumed(self):
        # One lot with enough value to meet target in one sell
        lot = _lot(purchase_price=100.0, qty=1000.0)
        target = 500.0  # very small — one partial sell suffices
        result = optimize(_portfolio(lot), self.PRICES, self.RATES, target_nis=target)
        assert len(result.recommendations) == 1
