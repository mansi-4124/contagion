import pytest
import respx
import httpx

from app.ingestion.edgar import (
    EdgarClient,
    CompanyNotFoundError,
)


@pytest.fixture
def client():
    return EdgarClient()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_company_cik_success(client):
    """
    Apple should resolve to its SEC CIK.
    """

    route = respx.get(
        "https://www.sec.gov/files/company_tickers.json"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "0": {
                    "cik_str": 320193,
                    "ticker": "AAPL",
                    "title": "Apple Inc."
                },
                "1": {
                    "cik_str": 789019,
                    "ticker": "MSFT",
                    "title": "Microsoft Corporation"
                },
            },
        )
    )

    cik = await client.fetch_company_cik("Apple")

    assert route.called
    assert cik == "0000320193"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_company_cik_case_insensitive(client):
    respx.get(
        "https://www.sec.gov/files/company_tickers.json"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "0": {
                    "cik_str": 320193,
                    "ticker": "AAPL",
                    "title": "Apple Inc."
                }
            },
        )
    )

    cik = await client.fetch_company_cik("apple")

    assert cik == "0000320193"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_company_cik_not_found(client):
    respx.get(
        "https://www.sec.gov/files/company_tickers.json"
    ).mock(
        return_value=httpx.Response(
            200,
            json={},
        )
    )

    with pytest.raises(CompanyNotFoundError):
        await client.fetch_company_cik("Some Random Company")