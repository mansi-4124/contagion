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

import asyncio
import json
import logging
import os
import random
from typing import Any

import httpx

# Update based on actual location of your configuration framework (Fix 2)
from app.config import settings

logger = logging.getLogger(__name__)

GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_TIMESPAN = "1h"
DEFAULT_MAX_RECORDS = 10  # Fix 3: Use maxrecords=10 during development (originally 25)
RATE_LIMIT_BASE_SLEEP_SECONDS = 10.0
MAX_RATE_LIMIT_RETRIES = 3

# Architecture Spec §6.2.4 step 2 keyword list
SUPPLY_CHAIN_QUERIES = [
    '"factory fire"',
    '"port strike"',
    '"chip shortage"',
    '"supply disruption"',
    '"export ban"',
    '"plant shutdown"',
]


class GdeltAPIError(Exception):
    """Raised on network failure, non-2xx response, or GDELT's plain-text

    query-validation error (e.g. keywords too short/long/common).
    """


def _looks_like_gdelt_error_text(body_text: str) -> bool:
    lowered = body_text.lower()
    return "too short" in lowered or "too long" in lowered or "too common" in lowered


def load_seed_news() -> list[dict[str, Any]]:
    """Fix 5: Helper to load bundled GDELT seed data from a JSON file when API fails or is rate-limited."""
    seed_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "seed_gdelt_news.json",
    )
    if os.path.exists(seed_path):
        try:
            with open(seed_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to parse GDELT seed file: %s", e)

    # Fallback inline stub if seed file doesn't exist yet
    return [
        {
            "title": "Global Supply Chains Face New Disruptions Amid Semiconductor Shocks",
            "url": "https://example.com/news/supply-chain-disruptions-2026",
            "seenpubdate": "20260704T120000Z",
            "seendescription": "",
            "domain": "example.com",
            "sourcecountry": "US",
            "language": "eng",
        }
    ]


async def _fetch_articles(query: str, timespan: str, max_records: int) -> list[dict]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "timespan": timespan,
        "maxrecords": str(max_records),
        "sort": "datedesc",
    }

    # Fix 2: Explicit User-Agent and headers
    headers = {
        "User-Agent": settings.sec.user_agent,
        "Accept": "application/json",
    }

    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(
                headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(GDELT_BASE_URL, params=params)
        except httpx.HTTPError as e:
            raise GdeltAPIError(f"Network error calling GDELT: {e}") from e

        if response.status_code == 429:
            attempt += 1
            if attempt > MAX_RATE_LIMIT_RETRIES:
                raise GdeltAPIError(
                    f"GDELT rate-limited after {attempt} attempts: {response.text[:200]}"
                )

            # Fix 4: Exponential backoff with random jitter (0 to 2 seconds)
            sleep_seconds = (
                RATE_LIMIT_BASE_SLEEP_SECONDS * (2 ** (attempt - 1))
                + random.uniform(0, 2)
            )
            logger.warning(
                "GDELT rate-limited (429) — retrying in %.1fs (attempt %d)",
                sleep_seconds,
                attempt,
            )
            await asyncio.sleep(sleep_seconds)
            continue

        if response.status_code >= 400:
            raise GdeltAPIError(
                f"GDELT returned HTTP {response.status_code}: {response.text[:200]}"
            )

        if _looks_like_gdelt_error_text(response.text):
            raise GdeltAPIError(
                f"GDELT rejected the query: {response.text[:200]}"
            )

        try:
            body = response.json()
        except ValueError as e:
            raise GdeltAPIError(
                f"GDELT response was not valid JSON: {response.text[:200]}"
            ) from e

        raw_articles = body.get("articles", [])
        return [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "seenpubdate": a.get("seendate", ""),
                "seendescription": "",
                "domain": a.get("domain", ""),
                "sourcecountry": a.get("sourcecountry", ""),
                "language": a.get("language", ""),
            }
            for a in raw_articles
        ]


async def fetch_supply_chain_news(
    timespan: str = DEFAULT_TIMESPAN,
) -> list[dict]:
    """Polls GDELT for recent supply-chain-relevant news across the fixed

    keyword list from Architecture Spec §6.2.4. Catches exceptions and falls back
    to committed repository seed data if a full failure occurs.
    """
    try:
        # Fix 1: Split into multiple smaller queries executed concurrently
        records_per_query = max(1, DEFAULT_MAX_RECORDS // len(SUPPLY_CHAIN_QUERIES))
        tasks = [
            _fetch_articles(q, timespan, records_per_query)
            for q in SUPPLY_CHAIN_QUERIES
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined_articles = {}
        for res in results:
            if isinstance(res, Exception):
                # Bubble up exceptions inside individual tasks to trigger seed fallback safely
                raise GdeltAPIError(f"Sub-query task failed: {res}") from res
            for article in res:
                # Merge and deduplicate records by URL
                combined_articles[article["url"]] = article

        return list(combined_articles.values())

    except GdeltAPIError as e:
        # Fix 5: Graceful fallback when rate-limited or encountering query rejection
        logger.warning(
            "GDELT query failure (%s). Falling back to bundled seed data.", e
        )
        return load_seed_news()


async def fetch_company_news(
    company_name: str, timespan: str = "7d"
) -> list[dict]:
    """Polls GDELT for recent news mentioning a specific company by name."""
    query = f'"{company_name}"'
    try:
        return await _fetch_articles(query, timespan, DEFAULT_MAX_RECORDS)
    except GdeltAPIError as e:
        logger.warning(
            "GDELT query failure for company %s (%s). Falling back to bundled seed data.",
            company_name,
            e,
        )
        return load_seed_news()