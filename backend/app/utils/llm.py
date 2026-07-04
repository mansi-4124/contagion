"""
Thin async wrapper around the Groq SDK -- the single boundary module the rest
of the app calls through (Architecture Spec §1: no other module imports a
third-party LLM SDK directly).

Two-tier model split per Task Plan D2-11:
  - call_synthesis()  -> llama-3.3-70b-versatile  (recommendations, risk-event
                          summarization -- higher quality, lower call volume)
  - call_extraction() -> llama-3.1-8b-instant      (structured extraction,
                          classification -- higher call volume, needs to be
                          cheap and fast)

Retries on Groq's 429 (rate limit) per Task Plan rule #7 / D2-11: sleep then
retry, up to max_retries times, before propagating the error.
"""
import asyncio

from groq import AsyncGroq, RateLimitError

from app.config.settings import settings

DEFAULT_RETRY_SLEEP_SECONDS = 3.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_MODEL = "llama-3.3-70b-versatile"

def _strip_provider_prefix(model: str) -> str:
    """
    "groq/llama-3.3-70b-versatile" -> "llama-3.3-70b-versatile"
 
    LiteLLM/Cognee's "provider/model" convention isn't understood by the
    native groq SDK, which wants just the model name. A bare model name
    with no "/" passes through unchanged.
    """
    return model.split("/", 1)[1] if "/" in model else model

class GroqClient:
    def __init__(
        self,
        api_key: str | None = None,
        synthesis_model: str | None = None,
        extraction_model: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_sleep_seconds: float = DEFAULT_RETRY_SLEEP_SECONDS,
    ):
        self._client = AsyncGroq(api_key=api_key or settings.llm.groq_api_key)
        configured_model = getattr(settings.llm, "model", None)
        default_model = _strip_provider_prefix(configured_model) if configured_model else DEFAULT_MODEL
        self.synthesis_model = (synthesis_model or getattr(settings.llm, "synthesis_model", None) or default_model)
        self.extraction_model = (extraction_model or getattr(settings.llm, "extraction_model", None) or default_model)
        self.max_retries = max_retries
        self.retry_sleep_seconds = retry_sleep_seconds

    async def _call(self, model: str, prompt: str, json_mode: bool = False) -> str:
        attempt = 0
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        while True:
            try:
                response = await self._client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except RateLimitError:
                attempt += 1
                if attempt > self.max_retries:
                    raise
                await asyncio.sleep(self.retry_sleep_seconds)

    async def call_synthesis(self, prompt: str) -> str:
        """Higher-quality model -- recommendations, risk-event summaries, free-text synthesis."""
        return await self._call(self.synthesis_model, prompt)

    async def call_extraction(self, prompt: str, json_mode:bool = True) -> str:
        """Cheaper/faster model -- structured extraction, classification, high call volume."""
        return await self._call(self.extraction_model, prompt, json_mode=json_mode)