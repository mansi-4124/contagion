"""
D2-07 — GDELT client
File: backend/app/ingestion/gdelt/client.py

fetch_supply_chain_news(timespan) — polls GDELT's DOC 2.0 API for recent
supply-chain-relevant news (Architecture Spec §6.2.4, feeds the 15-minute
alert_pipeline cycle).
fetch_company_news(company_name, timespan) — same API, scoped to one
company's name.

IMPORTANT — verified against the real API, not the task doc's assumed
shape:
  - Top-level JSON key is `articles`, not `artlist`.
  - Real per-article fields: title, url, url_mobile, seendate, domain,
    language, sourcecountry, socialimage.
  - There is NO description/snippet field anywhere in artlist mode. Our
    return contract keeps a `seendescription` key for compatibility with
    downstream code (D3's entity_extraction assumes "title + snippet" per
    Architecture Spec §6.2.4 step 3), but it is always "" here — there is
    no snippet to put in it. If D3 genuinely needs snippet-level text,
    that requires a separate full-article fetch per URL, which is a much
    heavier operation than a 15-minute poll cycle should do for every
    article; flag this to whoever builds entity_extraction rather than
    silently working around it here.
  - `seendate` maps to our `seenpubdate` key (naming kept from the task
    doc for compatibility; the underlying GDELT field is `seendate`).
  - Timespan minutes must use the "min" suffix ("15min"), not a bare "m"
    (ambiguous with GDELT's month suffix in its own timespan grammar).
  - Multi-word or overly generic single-word queries can trigger a
    plain-text (non-JSON) "keywords too short/long/common" error from
    GDELT even on a 200 response — this is handled explicitly below
    rather than silently parsed as zero results.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_TIMESPAN = "15min"
DEFAULT_MAX_RECORDS = 25  # matches Architecture Spec §6.2.4 step 2: "top 25 articles"

# Architecture Spec §6.2.4 step 2 keyword list
SUPPLY_CHAIN_KEYWORDS = (
    '"factory fire" OR "port strike" OR "chip shortage" OR '
    '"supply disruption" OR "export ban" OR "plant shutdown"'
)


class GdeltAPIError(Exception):
    """Raised on network failure, non-2xx response, or GDELT's plain-text
    query-validation error (e.g. keywords too short/long/common)."""


def _looks_like_gdelt_error_text(body_text: str) -> bool:
    lowered = body_text.lower()
    return "too short" in lowered or "too long" in lowered or "too common" in lowered


async def _fetch_articles(query: str, timespan: str, max_records: int) -> list[dict]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "timespan": timespan,
        "maxrecords": str(max_records),
        "sort": "datedesc",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(GDELT_BASE_URL, params=params)
    except httpx.HTTPError as e:
        raise GdeltAPIError(f"Network error calling GDELT: {e}") from e

    if response.status_code >= 400:
        raise GdeltAPIError(f"GDELT returned HTTP {response.status_code}: {response.text[:200]}")

    # GDELT returns 200 with a plain-text (non-JSON) error body for invalid
    # queries, rather than a proper error status — must check content before
    # attempting to parse as JSON.
    if _looks_like_gdelt_error_text(response.text):
        raise GdeltAPIError(f"GDELT rejected the query: {response.text[:200]}")

    try:
        body = response.json()
    except ValueError as e:
        raise GdeltAPIError(f"GDELT response was not valid JSON: {response.text[:200]}") from e

    raw_articles = body.get("articles", [])

    return [
        {
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "seenpubdate": a.get("seendate", ""),
            "seendescription": "",  # see module docstring — GDELT has no snippet field
            "domain": a.get("domain", ""),
            "sourcecountry": a.get("sourcecountry", ""),
            "language": a.get("language", ""),
        }
        for a in raw_articles
    ]


async def fetch_supply_chain_news(timespan: str = DEFAULT_TIMESPAN) -> list[dict]:
    """Polls GDELT for recent supply-chain-relevant news across the fixed
    keyword list from Architecture Spec §6.2.4. Raises GdeltAPIError on
    network/API failure — callers (alert_pipeline) should catch this and
    skip the cycle rather than crash, per Architecture Spec's general
    external-boundary error-handling philosophy."""
    return await _fetch_articles(SUPPLY_CHAIN_KEYWORDS, timespan, DEFAULT_MAX_RECORDS)


async def fetch_company_news(company_name: str, timespan: str = "7d") -> list[dict]:
    """Polls GDELT for recent news mentioning a specific company by name."""
    query = f'"{company_name}"'
    return await _fetch_articles(query, timespan, DEFAULT_MAX_RECORDS)