"""
Unit tests for app.utils.llm (D2-11, pulled forward as a dependency of D2-02).

The groq SDK's AsyncGroq client is mocked throughout -- these tests never make
a real network call. Retry-on-429 behavior (Task Plan rule #7 / D2-11) is
tested by making the mock raise groq.RateLimitError a fixed number of times
before succeeding.
"""
import groq
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.utils.llm import GroqClient


def make_fake_response(content: str):
    """Build a minimal object shaped like a groq ChatCompletion response."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def make_rate_limit_error():
    # groq.RateLimitError requires a response/body in real usage; a MagicMock
    # stands in fine since we never inspect its attributes in the client code.
    fake_response = MagicMock()
    fake_response.status_code = 429
    fake_response.headers = {}
    return groq.RateLimitError("rate limited", response=fake_response, body=None)


class TestGroqClientCallExtraction:
    @pytest.mark.asyncio
    async def test_returns_model_response_content(self):
        client = GroqClient(api_key="fake-key", retry_sleep_seconds=0)
        client._client.chat.completions.create = AsyncMock(
            return_value=make_fake_response('[{"supplier_name": "TSMC"}]')
        )

        result = await client.call_extraction("extract suppliers from: ...")

        assert result == '[{"supplier_name": "TSMC"}]'

    @pytest.mark.asyncio
    async def test_uses_extraction_model(self):
        client = GroqClient(
            api_key="fake-key",
            extraction_model="llama-3.1-8b-instant",
            retry_sleep_seconds=0,
        )
        mock_create = AsyncMock(return_value=make_fake_response("ok"))
        client._client.chat.completions.create = mock_create

        await client.call_extraction("some prompt")

        _, kwargs = mock_create.call_args
        assert kwargs["model"] == "llama-3.1-8b-instant"

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_then_succeeds(self):
        client = GroqClient(api_key="fake-key", max_retries=3, retry_sleep_seconds=0)
        mock_create = AsyncMock(
            side_effect=[make_rate_limit_error(), make_rate_limit_error(), make_fake_response("ok")]
        )
        client._client.chat.completions.create = mock_create

        with patch("app.utils.llm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await client.call_extraction("some prompt")

        assert result == "ok"
        assert mock_create.call_count == 3
        assert mock_sleep.call_count == 2  # slept before each of the 2 retries

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_retries(self):
        client = GroqClient(api_key="fake-key", max_retries=2, retry_sleep_seconds=0)
        mock_create = AsyncMock(side_effect=make_rate_limit_error())
        client._client.chat.completions.create = mock_create

        with patch("app.utils.llm.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(groq.RateLimitError):
                await client.call_extraction("some prompt")

        assert mock_create.call_count == 3  # initial attempt + 2 retries


class TestGroqClientCallSynthesis:
    @pytest.mark.asyncio
    async def test_uses_synthesis_model(self):
        client = GroqClient(
            api_key="fake-key",
            synthesis_model="llama-3.3-70b-versatile",
            retry_sleep_seconds=0,
        )
        mock_create = AsyncMock(return_value=make_fake_response("synthesized answer"))
        client._client.chat.completions.create = mock_create

        result = await client.call_synthesis("write a recommendation")

        _, kwargs = mock_create.call_args
        assert kwargs["model"] == "llama-3.3-70b-versatile"
        assert result == "synthesized answer"


class TestGroqClientDefaultsFromSettings:
    @pytest.mark.asyncio
    async def test_defaults_pull_from_settings_when_not_passed_explicitly(self):
        with patch("app.utils.llm.settings") as mock_settings:
            mock_settings.llm.groq_api_key = "settings-key"
            mock_settings.llm.synthesis_model = "llama-3.3-70b-versatile"
            mock_settings.llm.extraction_model = "llama-3.1-8b-instant"

            client = GroqClient()

            assert client.synthesis_model == "llama-3.3-70b-versatile"
            assert client.extraction_model == "llama-3.1-8b-instant"