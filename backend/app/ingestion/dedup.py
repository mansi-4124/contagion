"""
D2-09 — Event deduplication
File: backend/app/ingestion/dedup.py

event_fingerprint() — deterministic SHA256 hash of (event_type, location,
date_hour), used so the same real-world event reported by multiple GDELT
articles within the same hour doesn't fire duplicate alerts (Architecture
Spec §6.2.4 step 7).

is_duplicate()/mark_seen() — backed by Redis's own key TTL (SET ... EX),
not the Redis Set data structure: each fingerprint needs its own
independent 6h expiry, which a Set's members can't carry individually.
"""

import hashlib

from app.config.settings import settings
from app.infra.redis_client import get_redis_client

DEDUP_KEY_PREFIX = "dedup:"


def event_fingerprint(event_type: str, location: str, date_hour: str) -> str:
    """
    Deterministic fingerprint for an event, hour-granular so near-duplicate
    reports of the same real-world event within the same hour collapse to
    one fingerprint. Case- and whitespace-normalized: an LLM extraction
    step (Architecture Spec §6.2.4 step 4) may describe the same event
    with inconsistent casing across different source articles.
    """
    normalized = "|".join([
        event_type.strip().lower(),
        location.strip().lower(),
        date_hour.strip(),
    ])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def is_duplicate(fingerprint: str) -> bool:
    """True if this fingerprint was already mark_seen() within its TTL window."""
    client = get_redis_client()
    exists = await client.exists(f"{DEDUP_KEY_PREFIX}{fingerprint}")
    return exists > 0


async def mark_seen(fingerprint: str, ttl_seconds: int | None = None) -> None:
    """Records a fingerprint as seen, expiring after ttl_seconds (default:
    settings.redis.dedup_ttl_seconds, 6h per Architecture Spec §6.2.4)."""
    client = get_redis_client()
    ttl = ttl_seconds if ttl_seconds is not None else settings.redis.dedup_ttl_seconds
    await client.set(f"{DEDUP_KEY_PREFIX}{fingerprint}", "1", ex=ttl)