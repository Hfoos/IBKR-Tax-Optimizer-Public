"""
Bank of Israel (BOI) exchange rate client.

API used: https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/EXR/1.0/
Series keys: RER_USD_ILS, RER_GBP_ILS
Format: sdmx-json

Rates are cached locally in .rate_cache.json to avoid repeated API calls.
BOI only publishes rates on Israeli business days; we walk back up to 5 days
to find the most recent published rate for any given date.
"""

import json
import requests
from datetime import date, timedelta
from pathlib import Path

_CACHE_FILE = Path(__file__).parent.parent / ".rate_cache.json"
_BOI_BASE = (
    "https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/"
    "BOI.STATISTICS/EXR/1.0"
)
_SERIES = {
    "USD": "RER_USD_ILS",
    "GBP": "RER_GBP_ILS",
    "EUR": "RER_EUR_ILS",
}


def get_rate(currency: str, for_date: date) -> float:
    """Return the BOI representative NIS rate for the given currency and date.

    Falls back to the nearest prior business day if the exact date has no rate
    (weekends, Israeli holidays).
    """
    currency = currency.upper()
    if currency not in _SERIES:
        raise ValueError(f"Unsupported currency: {currency}. Supported: {list(_SERIES)}")

    cache = _load_cache()
    cache_key = f"{currency}_{for_date.isoformat()}"
    if cache_key in cache:
        return cache[cache_key]

    for delta in range(7):
        check_date = for_date - timedelta(days=delta)
        rate = _fetch_single_rate(currency, check_date)
        if rate is not None:
            cache[cache_key] = rate
            _save_cache(cache)
            return rate

    raise RuntimeError(
        f"Could not retrieve BOI exchange rate for {currency} on {for_date}. "
        "Check your internet connection or verify the BOI API is reachable."
    )


def prefetch_rates(currency: str, dates: list[date]) -> dict[date, float]:
    """Batch-fetch rates for a list of dates. Returns {date: rate}."""
    if not dates:
        return {}
    result = {}
    min_date = min(dates)
    max_date = max(dates)
    bulk = _fetch_range(currency, min_date, max_date)
    for d in dates:
        if d in bulk:
            result[d] = bulk[d]
        else:
            # walk back to find nearest prior rate
            for delta in range(7):
                prior = d - timedelta(days=delta)
                if prior in bulk:
                    result[d] = bulk[prior]
                    break
    return result


def _fetch_range(currency: str, start: date, end: date) -> dict[date, float]:
    """Fetch all rates for a currency between start and end dates from BOI."""
    series_key = _SERIES.get(currency.upper())
    if not series_key:
        return {}

    url = f"{_BOI_BASE}/{series_key}"
    params = {
        "startperiod": start.isoformat(),
        "endperiod": end.isoformat(),
        "format": "sdmx-json",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return _parse_sdmx_response(resp.json())
    except Exception:
        return {}


def _fetch_single_rate(currency: str, for_date: date) -> float | None:
    rates = _fetch_range(currency, for_date, for_date)
    return rates.get(for_date)


def _parse_sdmx_response(payload: dict) -> dict[date, float]:
    """Parse BOI SDMX-JSON response into {date: rate} dict."""
    result = {}
    try:
        data = payload["data"]
        structure = data["structure"]

        # TIME_PERIOD values are dicts with an "id" key holding "YYYY-MM-DD"
        obs_dims = structure["dimensions"]["observation"]
        time_dim = next(d for d in obs_dims if d["id"] == "TIME_PERIOD")
        date_values = time_dim["values"]  # list of {"id": "YYYY-MM-DD", ...}

        # Rates live under dataSets[0].series[key].observations
        dataset = data["dataSets"][0]
        for series_data in dataset["series"].values():
            for obs_key, obs_vals in series_data["observations"].items():
                idx = int(obs_key)
                rate_val = obs_vals[0]
                if rate_val is not None and idx < len(date_values):
                    d = date.fromisoformat(date_values[idx]["id"])
                    result[d] = float(rate_val)
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return result


def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    try:
        _CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass
