"""Geocoding service using OpenStreetMap Nominatim (free, no API key)."""

import time
import requests

_last_call = 0.0


def geocode_address(address: str) -> tuple[float | None, float | None, str]:
    """
    Convert a US address string to (latitude, longitude, display_name).
    Returns (None, None, "") if not found.
    Respects Nominatim's 1-request-per-second rate limit.
    """
    global _last_call
    # Rate limit: 1 req/sec
    elapsed = time.time() - _last_call
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }
    headers = {"User-Agent": "RouteOptimizerPOC/1.0"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        _last_call = time.time()
        results = resp.json()
        if results:
            r = results[0]
            return float(r["lat"]), float(r["lon"]), r.get("display_name", address)
    except Exception:
        pass

    return None, None, ""
