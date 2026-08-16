"""Unit tests for src/parser.py — using tmp_path CSV fixtures, no real data files."""
import csv
import pytest
from datetime import date
from pathlib import Path

from src.parser import parse_all_csvs, parse_open_positions, get_csv_filenames


# ── CSV row builders ──────────────────────────────────────────────────────────

def _trade_row(currency="USD", symbol="AAPL", trade_date="2022-06-15",
               quantity=100.0, price=150.0, commission=-1.5):
    """Build a minimal Trades data row matching the parser's expected format."""
    row = [""] * 12
    row[0] = "Trades"
    row[1] = "Data"
    row[2] = "Order"
    row[3] = "Stocks"
    row[4] = currency
    row[5] = symbol
    row[6] = trade_date
    row[7] = str(quantity)
    row[8] = str(price)
    row[9] = ""
    row[10] = ""
    row[11] = str(commission)
    return row


def _transfer_row(currency="USD", symbol="AAPL", transfer_date="2022-01-01",
                  quantity=100.0, total_cost=10000.0):
    """Build a Transfers In row."""
    row = [""] * 13
    row[0] = "Transfers"
    row[1] = "Data"
    row[2] = "Stocks"
    row[3] = currency
    row[4] = symbol
    row[5] = transfer_date
    row[6] = "ACAT"
    row[7] = "In"
    row[8] = "--"
    row[9] = "External"
    row[10] = str(quantity)
    row[11] = "--"
    row[12] = str(total_cost)
    return row


def _open_pos_row(symbol="AAPL", quantity=100.0):
    row = [""] * 7
    row[0] = "Open Positions"
    row[1] = "Data"
    row[2] = "Summary"
    row[3] = "Stocks"
    row[4] = ""
    row[5] = symbol
    row[6] = str(quantity)
    return row


def _write_csv(path: Path, rows: list[list[str]]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


# ── tests ─────────────────────────────────────────────────────────────────────

def test_trade_row_parsed_correctly(tmp_path):
    csv_file = tmp_path / "U1234567_2022_activity.csv"
    _write_csv(csv_file, [_trade_row(symbol="MSFT", quantity=50.0, price=300.0,
                                     commission=-2.0, trade_date="2022-03-10",
                                     currency="USD")])
    txns = parse_all_csvs(str(tmp_path))
    assert len(txns) == 1
    t = txns[0]
    assert t.symbol == "MSFT"
    assert t.quantity == pytest.approx(50.0)
    assert t.price == pytest.approx(300.0)
    assert t.commission == pytest.approx(2.0)   # always positive
    assert t.date == date(2022, 3, 10)
    assert t.currency == "USD"
    assert t.account == "U1234567"


def test_sell_trade_has_negative_quantity(tmp_path):
    csv_file = tmp_path / "U1234567_2022_activity.csv"
    _write_csv(csv_file, [_trade_row(quantity=-30.0)])
    txns = parse_all_csvs(str(tmp_path))
    assert txns[0].quantity == pytest.approx(-30.0)


def test_transfer_in_parsed_correctly(tmp_path):
    csv_file = tmp_path / "U1234567_2022_activity.csv"
    _write_csv(csv_file, [_transfer_row(symbol="AAPL", quantity=200.0,
                                        total_cost=20000.0)])
    txns = parse_all_csvs(str(tmp_path))
    assert len(txns) == 1
    t = txns[0]
    assert t.is_transfer is True
    assert t.quantity == pytest.approx(200.0)
    assert t.price == pytest.approx(100.0)  # total_cost / qty


def test_malformed_row_skipped(tmp_path):
    csv_file = tmp_path / "U1234567_2022_activity.csv"
    garbage = [["irrelevant", "row", "data"],
               ["Trades", "Header"],
               _trade_row(symbol="AAPL")]
    _write_csv(csv_file, garbage)
    txns = parse_all_csvs(str(tmp_path))
    assert len(txns) == 1
    assert txns[0].symbol == "AAPL"


def test_parse_all_csvs_aggregates_and_sorts_by_date(tmp_path):
    csv1 = tmp_path / "U1234567_2022_activity.csv"
    csv2 = tmp_path / "U1234567_2023_activity.csv"
    _write_csv(csv1, [_trade_row(trade_date="2022-06-01", quantity=100.0)])
    _write_csv(csv2, [_trade_row(trade_date="2023-01-15", quantity=-50.0)])
    txns = parse_all_csvs(str(tmp_path))
    assert len(txns) == 2
    assert txns[0].date < txns[1].date


def test_parse_open_positions_returns_correct_map(tmp_path):
    csv_file = tmp_path / "U9999999_2023_activity.csv"
    _write_csv(csv_file, [
        _open_pos_row("AAPL", 100.0),
        _open_pos_row("MSFT", 50.0),
    ])
    positions = parse_open_positions(str(tmp_path))
    assert "U9999999" in positions
    assert positions["U9999999"]["AAPL"] == pytest.approx(100.0)
    assert positions["U9999999"]["MSFT"] == pytest.approx(50.0)


def test_symbol_absent_from_open_positions_not_included(tmp_path):
    csv_file = tmp_path / "U9999999_2023_activity.csv"
    _write_csv(csv_file, [_open_pos_row("AAPL", 100.0)])
    positions = parse_open_positions(str(tmp_path))
    assert "MSFT" not in positions.get("U9999999", {})
