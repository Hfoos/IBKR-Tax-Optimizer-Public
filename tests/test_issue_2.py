"""Tests for IBKR Order Summary aggregation logic (issue #2)."""
import pytest
from datetime import date
from collections import OrderedDict

from src.optimizer import SellRecommendation, EventType


def _rec(account, symbol, currency, qty, price, proceeds_nis):
    return SellRecommendation(
        account=account,
        symbol=symbol,
        currency=currency,
        purchase_date=date(2022, 1, 1),
        qty_to_sell=qty,
        current_price=price,
        proceeds_nis=proceeds_nis,
        result_a_nis=0.0,
        result_b_nis=0.0,
        taxable_nis=0.0,
        event_type=EventType.GAIN,
        gross_tax_nis=0.0,
    )


def build_order_summary(recommendations):
    """Mirror the aggregation logic from app.py."""
    seen_keys = []
    groups = {}
    for rec in recommendations:
        key = (rec.account, rec.symbol)
        if key not in groups:
            seen_keys.append(key)
            groups[key] = {
                "Account": rec.account,
                "Symbol": rec.symbol,
                "Currency": rec.currency,
                "_shares": rec.qty_to_sell,
                "_price": rec.current_price,
                "_proceeds_nis": rec.proceeds_nis,
            }
        else:
            groups[key]["_shares"] += rec.qty_to_sell
            groups[key]["_proceeds_nis"] += rec.proceeds_nis

    rows = []
    for key in seen_keys:
        g = groups[key]
        rows.append({
            "Account": g["Account"],
            "Symbol": g["Symbol"],
            "Currency": g["Currency"],
            "Shares to Sell": g["_shares"],
            "Price": g["_price"],
            "Total Proceeds (NIS)": g["_proceeds_nis"],
        })
    return rows


def test_two_lots_same_symbol_same_account_merged():
    recs = [
        _rec("IB001", "AAPL", "USD", 100.0, 150.0, 50000.0),
        _rec("IB001", "AAPL", "USD", 50.0, 150.0, 25000.0),
    ]
    rows = build_order_summary(recs)
    assert len(rows) == 1
    assert rows[0]["Shares to Sell"] == pytest.approx(150.0)
    assert rows[0]["Total Proceeds (NIS)"] == pytest.approx(75000.0)


def test_same_symbol_different_accounts_separate_rows():
    recs = [
        _rec("IB001", "MSFT", "USD", 10.0, 300.0, 10000.0),
        _rec("IB002", "MSFT", "USD", 20.0, 300.0, 20000.0),
    ]
    rows = build_order_summary(recs)
    assert len(rows) == 2
    accounts = [r["Account"] for r in rows]
    assert "IB001" in accounts
    assert "IB002" in accounts


def test_row_order_follows_first_appearance():
    recs = [
        _rec("IB001", "GOOG", "USD", 5.0, 100.0, 1000.0),
        _rec("IB001", "AAPL", "USD", 10.0, 150.0, 3000.0),
        _rec("IB001", "GOOG", "USD", 5.0, 100.0, 1000.0),
    ]
    rows = build_order_summary(recs)
    assert len(rows) == 2
    assert rows[0]["Symbol"] == "GOOG"
    assert rows[1]["Symbol"] == "AAPL"


def test_single_lot_passthrough():
    recs = [_rec("IB001", "TSLA", "USD", 3.1234, 200.0, 5000.0)]
    rows = build_order_summary(recs)
    assert len(rows) == 1
    assert rows[0]["Shares to Sell"] == pytest.approx(3.1234)
    assert rows[0]["Price"] == pytest.approx(200.0)


def test_empty_recommendations_returns_empty():
    rows = build_order_summary([])
    assert rows == []


def test_proceeds_sum_equals_individual_lot_sum():
    recs = [
        _rec("IB001", "NVDA", "USD", 2.0, 500.0, 2200.0),
        _rec("IB001", "NVDA", "USD", 3.0, 500.0, 3300.0),
        _rec("IB001", "NVDA", "USD", 1.5, 500.0, 1650.0),
    ]
    rows = build_order_summary(recs)
    assert len(rows) == 1
    assert rows[0]["Total Proceeds (NIS)"] == pytest.approx(7150.0)
    assert rows[0]["Shares to Sell"] == pytest.approx(6.5)
