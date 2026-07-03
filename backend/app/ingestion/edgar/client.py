"""
Thin async client for SEC EDGAR — CIK lookup, 10-K filing discovery, and filing
text fetch. Architecture Spec §2 boundary module: nothing outside this file
imports SEC's APIs directly.

SEC requires every request to carry an identifying User-Agent (name + contact
email) or it will rate-limit or block the request outright. Set EDGAR_USER_AGENT
in .env before relying on this against real SEC traffic -- the fallback below
is a placeholder, not something to ship with.
"""
import os
import re

import httpx
from bs4 import BeautifulSoup

EDGAR_USER_AGENT = os.getenv(
    "EDGAR_USER_AGENT", "Contagion Hackathon Project contact@example.com"
)
HEADERS = {"User-Agent": EDGAR_USER_AGENT}

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik10}.json"
FILING_URL_TEMPLATE = (
    "https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{primary_document}"
)

MAX_FILING_CHARS = 50_000


class EdgarClientError(Exception):
    """Base class for EDGAR client failures the caller must handle."""


class CompanyNotFoundError(EdgarClientError):
    """No SEC-registered company matched the given name."""


class NoFilingFoundError(EdgarClientError):
    """The company's recent submissions contain no 10-K."""


async def _get_json(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url, headers=HEADERS, timeout=15.0)
    response.raise_for_status()
    return response.json()


async def fetch_company_cik(name: str, client: httpx.AsyncClient | None = None) -> str:
    """
    Resolve a company name to its 10-digit, zero-padded SEC CIK.

    Tries an exact (case-insensitive) title match first, so "Apple Inc." doesn't
    fall through to an unrelated substring match like "Apple Hospitality REIT".
    Falls back to a substring match if no exact match exists.

    Raises CompanyNotFoundError if nothing matches.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        data = await _get_json(client, TICKERS_URL)
        name_lower = name.strip().lower()

        exact = [row for row in data.values() if row["title"].strip().lower() == name_lower]
        if exact:
            return str(exact[0]["cik_str"]).zfill(10)

        substring = [row for row in data.values() if name_lower in row["title"].strip().lower()]
        if substring:
            return str(substring[0]["cik_str"]).zfill(10)

        raise CompanyNotFoundError(f"No SEC-registered company found matching '{name}'")
    finally:
        if owns_client:
            await client.aclose()


async def fetch_10k_filing_url(cik: str, client: httpx.AsyncClient | None = None) -> str:
    """
    Given a 10-digit CIK, return the URL of the most recent 10-K filing document.

    Raises NoFilingFoundError if the company's recent submissions contain no 10-K.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        submissions = await _get_json(client, SUBMISSIONS_URL_TEMPLATE.format(cik10=cik))
        recent = submissions["filings"]["recent"]
        forms = recent["form"]
        accession_numbers = recent["accessionNumber"]
        primary_documents = recent["primaryDocument"]

        for i, form in enumerate(forms):
            if form == "10-K":
                accession_no_dashes = accession_numbers[i].replace("-", "")
                cik_no_zeros = str(int(cik))
                return FILING_URL_TEMPLATE.format(
                    cik_no_zeros=cik_no_zeros,
                    accession_no_dashes=accession_no_dashes,
                    primary_document=primary_documents[i],
                )

        raise NoFilingFoundError(f"No 10-K filing found in recent submissions for CIK {cik}")
    finally:
        if owns_client:
            await client.aclose()


async def fetch_10k_text(url: str, client: httpx.AsyncClient | None = None) -> str:
    """
    Fetch a 10-K filing document and return the first MAX_FILING_CHARS characters
    of its plain text, with HTML tags stripped and whitespace collapsed.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        response = await client.get(url, headers=HEADERS, timeout=30.0)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:MAX_FILING_CHARS]
    finally:
        if owns_client:
            await client.aclose()