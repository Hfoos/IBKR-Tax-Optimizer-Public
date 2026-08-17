"""Unit tests for pure helper functions in app.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import format_nis, format_qty, event_badge, no_csv_message
from src.tax_engine import EventType


def test_format_nis_rounds_and_adds_symbol():
    assert format_nis(1234.6) == "₪1,235"


def test_format_nis_zero():
    assert format_nis(0) == "₪0"


def test_format_nis_large_with_comma():
    assert format_nis(100000.0) == "₪100,000"


def test_event_badge_gain():
    badge = event_badge(EventType.GAIN)
    assert "Gain" in badge
    assert "🔴" in badge


def test_event_badge_loss():
    badge = event_badge(EventType.LOSS)
    assert "Loss" in badge
    assert "🟢" in badge


def test_event_badge_zero():
    badge = event_badge(EventType.ZERO)
    assert "Zero event" in badge
    assert "⚪" in badge


def test_no_csv_message_is_plain_text():
    message = no_csv_message()
    assert "Place your IBKR activity statements" in message
    assert "here" in message
    assert "[here]" not in message
    assert "file:///" not in message
