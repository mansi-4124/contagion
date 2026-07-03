from __future__ import annotations

from typing import Any

import httpx

from app.config.settings import settings
from app.ingestion.edgar.exceptions import CompanyNotFoundError
from app.config.logging import get_logger


class EdgarClient:
    """
    Async client for interacting with the SEC EDGAR APIs.
    """

    BASE_URL = "https://www.sec.gov"

    def __init__(self) -> None:
        self.settings = settings
        self.logger = get_logger(__name__)

        self._headers = {
            "User-Agent": self.settings.sec.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov",
        }

    async def _get_json(self, url: str) -> dict[str, Any]:
        """
        Execute a GET request and return JSON.
        """

        self.logger.debug("Sending request", url=url)

        async with httpx.AsyncClient(
            headers=self._headers,
            timeout=self.settings.sec.timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)

        response.raise_for_status()

        self.logger.debug(
            "Received response",
            status=response.status_code,
            url=url,
        )

        return response.json()

    async def fetch_company_cik(self, company_name: str) -> str:
        """
        Resolve a company name to its SEC CIK.
        """

        companies = await self._get_json(
            f"{self.BASE_URL}/files/company_tickers.json"
        )

        company_name = company_name.lower().strip()

        for company in companies.values():
            title = company["title"].lower()

            if company_name in title:
                cik = str(company["cik_str"]).zfill(10)

                self.logger.info(
                    "Resolved company CIK",
                    company=company["title"],
                    cik=cik,
                )

                return cik

        raise CompanyNotFoundError(
            f"Unable to find company '{company_name}'."
        )