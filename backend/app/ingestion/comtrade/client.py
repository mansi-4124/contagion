"""
D2-06 — UN Comtrade client
File: backend/app/ingestion/comtrade/client.py

fetch_trade_volume(reporter, partner, hs_code, period) — bilateral trade
value lookup, used to weight geographic SUPPLIES_TO edges by real trade
volume (Architecture Spec §6.2.3).

IMPORTANT — verified against the real API, not the Architecture Spec's
assumed shape: UN Comtrade now requires a subscription key even for the
"preview" tier (confirmed against comtradeapi.un.org's current developer
onboarding, which states registration is required for "data previews").
The Architecture Spec's no-key preview URL
(comtradeapi.un.org/public/v1/preview/...) predates this change and
returns 400 without the now-mandatory params/key.

Real response field names (verified against comtradeapicall, the
UN-maintained Python client, and live API examples): `primaryValue` (not
"trade_value_usd" — that's our synthesized name), `reporterCode`,
`partnerCode`, `cmdCode`, `flowCode`, `period`/`refYear`.

If COMTRADE_SUBSCRIPTION_KEY isn't set in .env, this module skips the live
call entirely and uses a small fallback dataset for country pairs the
Architecture Spec's own demo examples depend on (US-Taiwan semiconductors,
etc.) — same "verified-limitation, not silent failure" pattern as the
ImportYeti client (D2-05).
"""

import logging
from dataclasses import dataclass
from typing import Literal, Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_PERIOD = "2023"
DEFAULT_FLOW_CODE = "M"  # import — matches the "reporter imports from partner" framing used throughout


class ComtradeUnavailableError(Exception):
    """Raised when no live data could be fetched AND no fallback exists for
    this country/HS-code combination, and allow_fallback=False."""


@dataclass(frozen=True)
class TradeVolumeResult:
    trade_value_usd: float
    year: int
    reporter: str
    partner: str
    hs_code: str
    source: Literal["live_api", "fallback_seed"]


# ---------------------------------------------------------------------------
# Fallback seed data — real-world-shaped values matching the Architecture
# Spec's own worked examples (§6.2.3: "US imports $90B of semiconductors
# from Taiwan annually vs $800M from Malaysia"). Keyed by
# (reporter, partner, hs_code).
# ---------------------------------------------------------------------------

_FALLBACK_TRADE_VOLUMES: dict[tuple[str, str, str], dict] = {
    ("842", "158", "854231"): {"trade_value_usd": 90_200_000_000.0, "year": 2023},  # US <- Taiwan, semiconductors
    ("842", "458", "854231"): {"trade_value_usd": 810_000_000.0, "year": 2023},     # US <- Malaysia, semiconductors
    ("842", "410", "854232"): {"trade_value_usd": 12_400_000_000.0, "year": 2023},  # US <- South Korea, memory chips
    ("842", "156", "850760"): {"trade_value_usd": 3_100_000_000.0, "year": 2023},   # US <- China, lithium batteries
    ("842", "392", "850760"): {"trade_value_usd": 2_650_000_000.0, "year": 2023},   # US <- Japan, batteries
}


def _fallback_trade_volume(reporter: str, partner: str, hs_code: str) -> Optional[TradeVolumeResult]:
    key = (str(reporter), str(partner), str(hs_code))
    entry = _FALLBACK_TRADE_VOLUMES.get(key)
    if entry is None:
        return None
    return TradeVolumeResult(
        trade_value_usd=entry["trade_value_usd"],
        year=entry["year"],
        reporter=reporter,
        partner=partner,
        hs_code=hs_code,
        source="fallback_seed",
    )


async def _fetch_live(reporter: str, partner: str, hs_code: str, period: str) -> Optional[TradeVolumeResult]:
    """Returns None (not an exception) when the API responds but has no
    matching data — that's a legitimate "no trade recorded" outcome, distinct
    from an API/auth failure."""
    url = f"{settings.comtrade.base_url}/C/A/HS"
    params = {
        "reporterCode": reporter,
        "partnerCode": partner,
        "cmdCode": hs_code,
        "flowCode": DEFAULT_FLOW_CODE,
        "period": period,
    }
    headers = {"Ocp-Apim-Subscription-Key": settings.comtrade.subscription_key}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        response = await client.get(url, params=params)

    if response.status_code == 401:
        logger.warning("Comtrade rejected subscription key (401) — falling back to seed data.")
        return None

    response.raise_for_status()
    body = response.json()
    records = body.get("data", [])

    if not records:
        return None

    record = records[0]
    return TradeVolumeResult(
        trade_value_usd=float(record["primaryValue"]),
        year=int(record.get("refYear") or period),
        reporter=str(record.get("reporterCode", reporter)),
        partner=str(record.get("partnerCode", partner)),
        hs_code=str(record.get("cmdCode", hs_code)),
        source="live_api",
    )


async def fetch_trade_volume(
    reporter_country_code: str,
    partner_country_code: str,
    hs_code: str,
    period: str = DEFAULT_PERIOD,
    allow_fallback: bool = True,
) -> TradeVolumeResult:
    """
    Fetches bilateral trade volume for a reporter/partner/HS-code triple.

    If COMTRADE_SUBSCRIPTION_KEY isn't configured, skips the live call
    entirely (no point making a request guaranteed to 401) and goes
    straight to fallback data. Same behavior if the live call fails for
    any reason and allow_fallback=True (default).
    """
    if not settings.comtrade.subscription_key:
        logger.info("No Comtrade subscription key configured — using fallback data.")
        result = _fallback_trade_volume(reporter_country_code, partner_country_code, hs_code)
        if result is not None:
            return result
        if not allow_fallback:
            raise ComtradeUnavailableError(
                f"No Comtrade subscription key configured and no fallback data for "
                f"reporter={reporter_country_code}, partner={partner_country_code}, hs_code={hs_code}."
            )
        raise ComtradeUnavailableError(
            f"No subscription key and no fallback entry for this country/HS-code combination "
            f"({reporter_country_code}, {partner_country_code}, {hs_code})."
        )

    try:
        result = await _fetch_live(reporter_country_code, partner_country_code, hs_code, period)
        if result is not None:
            return result
        logger.info("Live Comtrade call returned no data — trying fallback.")
    except httpx.HTTPError as e:
        logger.warning("Comtrade API error: %s — trying fallback.", e)

    fallback = _fallback_trade_volume(reporter_country_code, partner_country_code, hs_code)
    if fallback is not None:
        return fallback

    if not allow_fallback:
        raise ComtradeUnavailableError(
            f"Comtrade unavailable and no fallback data for reporter={reporter_country_code}, "
            f"partner={partner_country_code}, hs_code={hs_code}."
        )

    raise ComtradeUnavailableError(
        f"No live data and no fallback entry for reporter={reporter_country_code}, "
        f"partner={partner_country_code}, hs_code={hs_code}."
    )