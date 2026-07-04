"""
Normalizes company name variants (aliases, legal suffixes, abbreviations) to
a single canonical short name via Groq, so the same real-world entity doesn't
end up as separate nodes in the graph -- "TSMC" and "Taiwan Semiconductor
Manufacturing Company" must resolve to one node, not two.

A local in-process cache avoids re-calling Groq for a name string already
seen -- during seeding, the same supplier name often appears across multiple
companies' filings (e.g. TSMC shows up in Apple's, Nvidia's, and Tesla's
supplier lists).

Important limitation: the cache is keyed by the input string, not by
real-world entity. "TSMC" and "Taiwan Semiconductor" are different cache
keys and are looked up independently -- the cache cannot make two different
input strings converge on the same answer, only Groq's own consistency can.
This is why the model is asked for a single, well-known canonical form
(a recognizable short name) rather than a full legal name, which has far
more formatting variance and is less likely to come back identical across
different input aliases.
"""
from app.utils.llm import GroqClient

_cache: dict[str, str] = {}


def _cache_key(name: str) -> str:
    return name.strip().lower()


def _clean_response(raw: str) -> str:
    cleaned = raw.strip()
    if len(cleaned) >= 2 and cleaned[0] in "\"'" and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1].strip()
    return cleaned.rstrip(".")


def _build_prompt(name: str) -> str:
    return (
        "What is the single most widely-recognized short/common name used to "
        f"refer to this company: '{name}'?\n\n"
        "Examples:\n"
        "  'Taiwan Semiconductor Manufacturing Company' -> TSMC\n"
        "  'International Business Machines Corporation' -> IBM\n"
        "  'Apple Inc.' -> Apple\n\n"
        "Respond with ONLY the canonical short name, no punctuation, no explanation."
    )


async def normalize_company_name(name: str, llm: GroqClient | None = None) -> str:
    """
    Resolve a company name (any alias, legal form, or abbreviation) to a
    single canonical short name via Groq. Cached in-process by the
    lowercased/stripped input string, so repeated lookups of the exact same
    input never re-call Groq.
    """
    key = _cache_key(name)
    if key in _cache:
        return _cache[key]

    llm = llm or GroqClient()
    prompt = _build_prompt(name)
    raw_response = await llm.call_extraction(prompt, json_mode=False)
    canonical = _clean_response(raw_response)

    _cache[key] = canonical
    return canonical