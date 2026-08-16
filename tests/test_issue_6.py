"""Tests for smart quantity formatting helper (issue #6)."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import format_qty


def test_whole_number_no_decimals():
    assert format_qty(100.0) == "100"


def test_whole_number_with_comma():
    assert format_qty(1000.0) == "1,000"


def test_fractional_keeps_four_decimals():
    assert format_qty(100.1234) == "100.1234"


def test_non_zero_trailing_zeros_kept():
    assert format_qty(100.1000) == "100.1000"


def test_small_fractional():
    assert format_qty(0.0001) == "0.0001"


def test_zero_is_whole():
    assert format_qty(0.0) == "0"


def test_large_whole_number():
    assert format_qty(1_000_000.0) == "1,000,000"


def test_negative_whole_number():
    assert format_qty(-50.0) == "-50"


def test_float_precision_whole():
    # Values that are mathematically whole but represented as float
    assert format_qty(10.0) == "10"


def test_fractional_less_than_one():
    assert format_qty(0.5) == "0.5000"
