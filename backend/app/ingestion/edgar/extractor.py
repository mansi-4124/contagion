"""
Calls Groq to extract a structured supplier list from raw 10-K filing text.
Consumes app.ingestion.edgar.client.fetch_10k_text's output directly.

Uses app.utils.llm.GroqClient's extraction-tier model (llama-3.1-8b-instant
per Task Plan D2-11) -- structured extraction is high call volume across
5 companies x 1 filing each during seeding, so the cheaper/faster model fits.
"""
import json
import re

from pydantic import BaseModel, ValidationError

from app.utils.llm import GroqClient

# Groq's extraction-tier model has a token budget (free-tier TPM limits are
# tight -- see the 413 seen in production), so the prompt can't just include
# the whole 50,000-char filing. Naively taking text[:N] is worse than useless:
# the first N chars of a 10-K are SEC cover-page boilerplate (registrant info,
# filer-status checkboxes, table of contents) -- the actual supplier language
# usually lives in Item 1 (Business) or Item 1A (Risk Factors), often well
# past char 20,000. _extract_relevant_excerpts finds keyword hits anywhere in
# the document and pulls context windows around them instead.
MAX_PROMPT_TEXT_CHARS = 5_000

SUPPLIER_KEYWORDS = [
    "supplier", "suppliers", "single source", "sole source", "single-source",
    "sole-source", "manufacturing partner", "contract manufacturer", "foundry",
    "outsourc", "fabricat", "component supplier", "assembly partner",
]

_CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_relevant_excerpts(text: str, max_total_chars: int, window: int = 1000) -> str:
    """
    Find every occurrence of a supplier-related keyword and pull a window of
    surrounding context, merging overlapping windows, capped to
    max_total_chars total. Falls back to the document head if no keyword
    appears at all (better than sending nothing).
    """
    lower_text = text.lower()
    half_window = window // 2
    spans: list[tuple[int, int]] = []

    for keyword in SUPPLIER_KEYWORDS:
        search_start = 0
        while True:
            idx = lower_text.find(keyword, search_start)
            if idx == -1:
                break
            spans.append((max(0, idx - half_window), min(len(text), idx + len(keyword) + half_window)))
            search_start = idx + len(keyword)

    if not spans:
        return text[:max_total_chars]

    spans.sort()
    merged: list[list[int]] = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    excerpt = "\n[...]\n".join(text[start:end] for start, end in merged)
    return excerpt[:max_total_chars]


class ExtractedSupplier(BaseModel):
    supplier_name: str
    component_supplied: str
    country: str | None = None
    exclusivity: str | None = None  # e.g. "sole" | "primary" | "secondary" | None
    risk_notes: str | None = None


class ExtractionParseError(Exception):
    """Raised when the model's response can't be parsed into a supplier list."""


def _build_prompt(text: str, company_name: str) -> str:
    relevant_text = _extract_relevant_excerpts(text, MAX_PROMPT_TEXT_CHARS)
    return (
        f"You are extracting supplier relationships from {company_name}'s SEC 10-K filing.\n\n"
        "Read the filing text below and identify every named supplier mentioned. "
        "Return ONLY a JSON array (no prose, no markdown fences) where each element has "
        "exactly these fields:\n"
        '  - "supplier_name": string, the supplier\'s name\n'
        '  - "component_supplied": string, what they supply\n'
        '  - "country": string or null, the supplier\'s primary country of operation\n'
        '  - "exclusivity": one of "sole", "primary", "secondary", or null if unclear\n'
        '  - "risk_notes": string or null, any risk/concentration language the filing uses '
        "about this supplier\n\n"
        "If no suppliers are named, return an empty array: []\n\n"
        f"Filing text:\n{relevant_text}"
    )


def _strip_code_fences(raw: str) -> str:
    return _CODE_FENCE_PATTERN.sub("", raw.strip())


async def extract_suppliers_from_text(
    text: str, company_name: str, llm: GroqClient | None = None
) -> list[ExtractedSupplier]:
    """
    Extract named suppliers from 10-K filing text via Groq.

    Malformed individual entries (e.g. missing a required field) are skipped
    rather than failing the whole batch -- one bad entry from the model
    shouldn't discard four good ones. Raises ExtractionParseError only if the
    response as a whole isn't parseable JSON, or isn't a JSON array at all.
    """
    llm = llm or GroqClient()
    prompt = _build_prompt(text, company_name)
    raw_response = await llm.call_extraction(prompt)

    cleaned = _strip_code_fences(raw_response)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ExtractionParseError(
            f"Model response was not valid JSON: {raw_response!r}"
        ) from exc

    if isinstance(parsed, dict):
        # Groq's json_object response_format can't return a bare top-level
        # array -- it wraps one under some key (e.g. {"data": [...]}).
        # Unwrap it if there's exactly one list-valued key; otherwise fall
        # through to the error below rather than guessing which key is right.
        list_values = [v for v in parsed.values() if isinstance(v, list)]
        if len(list_values) == 1:
            parsed = list_values[0]

    if not isinstance(parsed, list):
        raise ExtractionParseError(
            f"Expected a JSON array of suppliers (optionally wrapped in a single-key "
            f"object), got {type(parsed).__name__}: {parsed!r}"
        )

    suppliers: list[ExtractedSupplier] = []
    for entry in parsed:
        try:
            suppliers.append(ExtractedSupplier(**entry))
        except (ValidationError, TypeError):
            continue  # skip malformed entries, keep the rest

    return suppliers