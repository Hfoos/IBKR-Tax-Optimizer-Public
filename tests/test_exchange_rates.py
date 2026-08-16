"""Unit tests for src/exchange_rates.py — no real HTTP calls."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from src.exchange_rates import get_rate, _parse_sdmx_response


# ── helpers ───────────────────────────────────────────────────────────────────

def _sdmx_payload(date_strs: list[str], rates: list[float]) -> dict:
    """Build a minimal SDMX-JSON payload matching the BOI API structure."""
    observations = {str(i): [r, 0, 0] for i, r in enumerate(rates)}
    return {
        "data": {
            "structure": {
                "dimensions": {
                    "observation": [
                        {
                            "id": "TIME_PERIOD",
                            "values": [{"id": d} for d in date_strs],
                        }
                    ]
                }
            },
            "dataSets": [
                {
                    "series": {
                        "0:0:0:0:0": {
                            "observations": observations
                        }
                    }
                }
            ],
        }
    }


# ── _parse_sdmx_response ──────────────────────────────────────────────────────

def test_parse_sdmx_extracts_date_rate_mapping():
    payload = _sdmx_payload(["2024-01-02", "2024-01-03"], [3.65, 3.70])
    result = _parse_sdmx_response(payload)
    assert result[date(2024, 1, 2)] == pytest.approx(3.65)
    assert result[date(2024, 1, 3)] == pytest.approx(3.70)


def test_parse_sdmx_returns_empty_on_malformed():
    assert _parse_sdmx_response({}) == {}
    assert _parse_sdmx_response({"data": {}}) == {}


# ── get_rate ──────────────────────────────────────────────────────────────────

@patch("src.exchange_rates._load_cache", return_value={})
@patch("src.exchange_rates._save_cache")
@patch("src.exchange_rates._fetch_range")
def test_known_currency_returns_positive_float(mock_fetch, _save, _load):
    for_date = date(2024, 1, 2)
    mock_fetch.return_value = {for_date: 3.65}
    rate = get_rate("USD", for_date)
    assert isinstance(rate, float)
    assert rate > 0


@patch("src.exchange_rates._load_cache", return_value={})
@patch("src.exchange_rates._save_cache")
def test_unsupported_currency_raises(_, __):
    with pytest.raises(ValueError, match="Unsupported currency"):
        get_rate("XYZ", date(2024, 1, 2))


@patch("src.exchange_rates._fetch_single_rate")
@patch("src.exchange_rates._save_cache")
def test_cache_hit_skips_http(mock_save, mock_fetch):
    for_date = date(2024, 1, 2)
    cache_key = f"USD_{for_date.isoformat()}"
    with patch("src.exchange_rates._load_cache", return_value={cache_key: 3.65}):
        rate = get_rate("USD", for_date)
    assert rate == pytest.approx(3.65)
    mock_fetch.assert_not_called()


@patch("src.exchange_rates._load_cache", return_value={})
@patch("src.exchange_rates._save_cache")
@patch("src.exchange_rates._fetch_range")
def test_fallback_to_nearest_prior_date(mock_fetch, _save, _load):
    target_date = date(2024, 1, 7)  # e.g. a Sunday
    prior_date = target_date - timedelta(days=1)
    # Only prior_date has a rate, exact date does not
    mock_fetch.side_effect = lambda currency, start, end: (
        {prior_date: 3.72} if start == prior_date else {}
    )
    rate = get_rate("USD", target_date)
    assert rate == pytest.approx(3.72)
