"""
Unit tests for app.ingestion.edgar.normalizer (D2-03).

app.utils.llm.GroqClient is mocked throughout -- no real Groq calls here.
The integration test (real Groq, checking 'TSMC' and 'Taiwan Semiconductor'
converge on the same canonical name -- D2-03's literal "Done When") lives in
tests/integration/ingestion/edgar/test_normalizer_integration.py.

An autouse fixture clears the module-level cache before every test --
normalizer._cache is process-global state, and tests that don't isolate it
from each other (or from the integration suite, if run in the same process)
will get spurious cache hits instead of exercising the code under test.
"""
from unittest.mock import AsyncMock

import pytest

from app.ingestion.edgar import normalizer
from app.ingestion.edgar.normalizer import normalize_company_name


@pytest.fixture(autouse=True)
def clear_normalizer_cache():
    normalizer._cache.clear()
    yield
    normalizer._cache.clear()


def make_mock_llm(response_text: str):
    llm = AsyncMock()
    llm.call_extraction = AsyncMock(return_value=response_text)
    return llm


class TestNormalizeCompanyName:
    @pytest.mark.asyncio
    async def test_returns_canonical_name_from_llm_response(self):
        llm = make_mock_llm("TSMC")

        result = await normalize_company_name("Taiwan Semiconductor Manufacturing Co Ltd", llm=llm)

        assert result == "TSMC"

    @pytest.mark.asyncio
    async def test_passes_name_into_the_prompt(self):
        llm = make_mock_llm("IBM")

        await normalize_company_name("International Business Machines Corporation", llm=llm)

        sent_prompt = llm.call_extraction.call_args[0][0]
        assert "International Business Machines Corporation" in sent_prompt

    @pytest.mark.asyncio
    async def test_strips_wrapping_quotes_from_response(self):
        llm = make_mock_llm('"TSMC"')

        result = await normalize_company_name("Taiwan Semiconductor", llm=llm)

        assert result == "TSMC"

    @pytest.mark.asyncio
    async def test_strips_trailing_period_from_response(self):
        llm = make_mock_llm("TSMC.")

        result = await normalize_company_name("Taiwan Semiconductor", llm=llm)

        assert result == "TSMC"

    @pytest.mark.asyncio
    async def test_strips_surrounding_whitespace_from_response(self):
        llm = make_mock_llm("  TSMC  \n")

        result = await normalize_company_name("Taiwan Semiconductor", llm=llm)

        assert result == "TSMC"

    @pytest.mark.asyncio
    async def test_caches_result_and_does_not_recall_llm_for_same_input(self):
        llm = make_mock_llm("TSMC")

        first = await normalize_company_name("Taiwan Semiconductor Manufacturing Company", llm=llm)
        second = await normalize_company_name("Taiwan Semiconductor Manufacturing Company", llm=llm)

        assert first == second == "TSMC"
        assert llm.call_extraction.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_lookup_is_case_and_whitespace_insensitive(self):
        llm = make_mock_llm("TSMC")

        await normalize_company_name("Taiwan Semiconductor Manufacturing Company", llm=llm)
        await normalize_company_name("  taiwan semiconductor manufacturing company  ", llm=llm)

        assert llm.call_extraction.call_count == 1

    @pytest.mark.asyncio
    async def test_different_input_strings_each_call_the_llm_independently(self):
        # "TSMC" and "Taiwan Semiconductor" are different cache keys -- the
        # cache alone can't make them converge, only consistent LLM output can.
        # This test just confirms both actually reach the LLM (no accidental
        # cross-key cache hit), not that they produce the same answer --
        # that convergence claim belongs in the integration test.
        llm = make_mock_llm("TSMC")

        await normalize_company_name("TSMC", llm=llm)
        await normalize_company_name("Taiwan Semiconductor", llm=llm)

        assert llm.call_extraction.call_count == 2

    @pytest.mark.asyncio
    async def test_calls_llm_with_json_mode_disabled(self):
        llm = make_mock_llm("TSMC")
 
        await normalize_company_name("Taiwan Semiconductor", llm=llm)
 
        _, kwargs = llm.call_extraction.call_args
        assert kwargs.get("json_mode") is False

    @pytest.mark.asyncio
    async def test_cache_persists_across_separate_calls_without_explicit_llm_reuse(self):
        # Simulates two call sites in the app each constructing their own
        # GroqClient -- the cache is module-level, not tied to one client.
        llm_a = make_mock_llm("Apple")
        llm_b = make_mock_llm("Apple")

        first = await normalize_company_name("Apple Inc.", llm=llm_a)
        second = await normalize_company_name("Apple Inc.", llm=llm_b)

        assert first == second == "Apple"
        assert llm_a.call_extraction.call_count == 1
        assert llm_b.call_extraction.call_count == 0  # served from cache, never reached llm_b