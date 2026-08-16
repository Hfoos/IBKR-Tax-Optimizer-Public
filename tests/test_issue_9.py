"""Tests for IBKR Order Summary full-close flagging logic (issue #9)."""
import pytest
from datetime import date
from collections import deque
from src.optimizer import SellRecommendation
from src.portfolio import Lot
from src.tax_engine import EventType

TOLERANCE = 1e-4


def _lot(qty, symbol="AAPL", account="IB001"):
    return Lot(
        account=account, symbol=symbol, currency="USD",
        purchase_date=date(2021, 1, 1),
        original_qty=qty, remaining_qty=qty,
        purchase_price=100.0, purchase_commission=0.0, purchase_rate=3.5,
    )


def _rec(qty, symbol="AAPL", account="IB001"):
    return SellRecommendation(
        account=account, symbol=symbol, currency="USD",
        purchase_date=date(2021, 1, 1),
        qty_to_sell=qty, current_price=150.0,
        proceeds_nis=qty * 150.0 * 3.7,
        result_a_nis=1000.0, result_b_nis=800.0,
        taxable_nis=800.0, event_type=EventType.GAIN, gross_tax_nis=200.0,
        purchase_price=100.0, purchase_commission=0.0,
        original_qty=qty, purchase_rate=3.5, sale_rate=3.7,
    )


def _build_summary(recommendations, portfolio):
    """Mirror the IBKR Order Summary aggregation + full-close logic from app.py."""
    seen_keys = []
    groups = {}
    for rec in recommendations:
        key = (rec.account, rec.symbol)
        if key not in groups:
            seen_keys.append(key)
            groups[key] = {
                "Account": rec.account,
                "Symbol": rec.symbol,
                "_shares": rec.qty_to_sell,
                "_proceeds_nis": rec.proceeds_nis,
            }
        else:
            groups[key]["_shares"] += rec.qty_to_sell
            groups[key]["_proceeds_nis"] += rec.proceeds_nis

    rows = []
    for key in seen_keys:
        g = groups[key]
        total_held = sum(lot.remaining_qty for lot in portfolio[key])
        is_full_close = abs(g["_shares"] - total_held) < TOLERANCE
        rows.append({
            "Account": g["Account"],
            "Symbol": g["Symbol"],
            "Shares to Sell": g["_shares"],
            "Total Proceeds (NIS)": g["_proceeds_nis"],
            "Status": "⚠ Full close" if is_full_close else "",
        })
    return rows


def test_full_sell_flagged_as_full_close():
    portfolio = {("IB001", "AAPL"): deque([_lot(100.0)])}
    rows = _build_summary([_rec(100.0)], portfolio)
    assert rows[0]["Status"] == "⚠ Full close"


def test_partial_sell_has_empty_status():
    portfolio = {("IB001", "AAPL"): deque([_lot(100.0)])}
    rows = _build_summary([_rec(60.0)], portfolio)
    assert rows[0]["Status"] == ""


def test_two_lots_full_close_across_lots():
    portfolio = {("IB001", "AAPL"): deque([_lot(40.0), _lot(60.0)])}
    recs = [_rec(40.0), _rec(60.0)]
    rows = _build_summary(recs, portfolio)
    assert rows[0]["Status"] == "⚠ Full close"


def test_two_lots_partial_sell_no_flag():
    portfolio = {("IB001", "AAPL"): deque([_lot(40.0), _lot(60.0)])}
    recs = [_rec(40.0), _rec(30.0)]  # sells 70 of 100
    rows = _build_summary(recs, portfolio)
    assert rows[0]["Status"] == ""


def test_floating_point_tolerance_accepted():
    portfolio = {("IB001", "AAPL"): deque([_lot(100.0)])}
    recs = [_rec(100.0 - 5e-5)]  # within 1e-4
    rows = _build_summary(recs, portfolio)
    assert rows[0]["Status"] == "⚠ Full close"


def test_outside_tolerance_not_flagged():
    portfolio = {("IB001", "AAPL"): deque([_lot(100.0)])}
    recs = [_rec(99.9)]  # 0.1 difference — well outside 1e-4
    rows = _build_summary(recs, portfolio)
    assert rows[0]["Status"] == ""


def test_different_accounts_checked_independently():
    portfolio = {
        ("IB001", "AAPL"): deque([_lot(100.0, account="IB001")]),
        ("IB002", "AAPL"): deque([_lot(50.0, account="IB002")]),
    }
    recs = [
        _rec(100.0, account="IB001"),  # full close
        _rec(30.0, account="IB002"),   # partial
    ]
    rows = _build_summary(recs, portfolio)
    statuses = {r["Account"]: r["Status"] for r in rows}
    assert statuses["IB001"] == "⚠ Full close"
    assert statuses["IB002"] == ""
