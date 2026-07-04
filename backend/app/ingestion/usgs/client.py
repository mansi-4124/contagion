"""
D2-08 — USGS earthquake client
File: backend/app/ingestion/usgs/client.py

fetch_significant_earthquakes(min_magnitude) — polls USGS for recent
earthquakes above a magnitude threshold, feeding the alert_pipeline's
disaster-monitoring leg (Architecture Spec §6.2.5).

IMPORTANT — uses the FDSN Event Web Service
(earthquake.usgs.gov/fdsnws/event/1/query), NOT the fixed-threshold
summary feeds (e.g. significant_week.geojson, 4.5_week.geojson) that the
task doc's function signature implies. Those summary feeds only come in
preset magnitude buckets (2.5, 4.5, significant, etc.) — they don't accept
an arbitrary min_magnitude value. The FDSN query endpoint does, via a real
`minmagnitude` parameter, and needs no API key.

Verified field mapping:
  - properties.mag -> magnitude
  - properties.place -> place
  - properties.time -> epoch milliseconds; converted to ISO 8601 UTC here
  - geometry.coordinates -> [longitude, latitude, depth_km] IN THAT ORDER
    per the GeoJSON spec. This is the most common bug in USGS integrations
    — swapping lat/lon silently produces wrong-hemisphere results with no
    error, since both are valid floats.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

USGS_BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_LOOKBACK_DAYS = 7  # Architecture Spec §6.2.5: "significant earthquakes from last 7 days"


class UsgsAPIError(Exception):
    """Raised on network failure, non-2xx response, or malformed JSON."""


def _epoch_ms_to_iso(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


async def fetch_significant_earthquakes(
    min_magnitude: float = 5.5,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[dict]:
    """
    Returns a list of {magnitude, place, time, latitude, longitude, depth_km}
    for earthquakes at or above min_magnitude in the last `lookback_days`
    days. Returns an empty list if none match — this is a valid, expected
    outcome (per Done When), not an error condition.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=lookback_days)

    params = {
        "format": "geojson",
        "starttime": start.strftime("%Y-%m-%d"),
        "endtime": now.strftime("%Y-%m-%d"),
        "minmagnitude": str(min_magnitude),
        "orderby": "time",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(USGS_BASE_URL, params=params)
    except httpx.HTTPError as e:
        raise UsgsAPIError(f"Network error calling USGS: {e}") from e

    if response.status_code >= 400:
        raise UsgsAPIError(f"USGS returned HTTP {response.status_code}: {response.text[:200]}")

    try:
        body = response.json()
    except ValueError as e:
        raise UsgsAPIError(f"USGS response was not valid JSON: {response.text[:200]}") from e

    features = body.get("features", [])

    results = []
    for feature in features:
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [None, None, None])
        longitude, latitude, depth_km = coords[0], coords[1], coords[2]

        results.append({
            "magnitude": props.get("mag"),
            "place": props.get("place", ""),
            "time": _epoch_ms_to_iso(props["time"]) if props.get("time") else None,
            "latitude": latitude,
            "longitude": longitude,
            "depth_km": depth_km,
        })

    return results