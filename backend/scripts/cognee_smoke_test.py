"""Smoke test: Cognee remember → cognify → recall with Groq + FastEmbed."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.chdir(BACKEND_ROOT)

from app.config.logging import configure_logging, get_logger
from app.config.settings import settings

configure_logging()
log = get_logger(__name__)

SMOKE_DATASET = "contagion_smoke_test"
SMOKE_TEXT = "TSMC supplies semiconductor chips to Apple from Taiwan."


async def resolve_remember_result(result: object) -> tuple[str, object]:
    """Normalize local RememberResult promises vs cloud JSON dict responses."""
    if hasattr(result, "__await__"):
        result = await result

    if isinstance(result, dict):
        status = result.get("status") or result.get("state") or "completed"
        return str(status), result

    status = getattr(result, "status", "completed")
    return str(status), result


def format_recall_item(item: object) -> str:
    """Print recall results consistently for local models and cloud JSON."""
    if isinstance(item, dict):
        for key in ("text", "value", "answer", "content"):
            value = item.get(key)
            if value:
                return str(value)
        raw = item.get("raw")
        if isinstance(raw, dict) and raw.get("value"):
            return str(raw["value"])
        return str(item)

    text = getattr(item, "text", None)
    if text:
        return str(text)

    raw = getattr(item, "raw", None)
    if isinstance(raw, dict) and raw.get("value"):
        return str(raw["value"])

    return str(item)


def configure_cognee_environment() -> None:
    """Push Contagion settings into os.environ for Cognee to read."""
    llm = settings.llm
    embedding = settings.embedding
    cognee_cfg = settings.cognee

    env_map = {
        "LLM_PROVIDER": llm.provider,
        "LLM_MODEL": llm.model,
        "LLM_API_KEY": llm.api_key,
        "LLM_ENDPOINT": llm.base_url,
        "EMBEDDING_PROVIDER": embedding.provider,
        "EMBEDDING_MODEL": embedding.model,
        "EMBEDDING_DIMENSIONS": str(embedding.dimensions),
        "COGNEE_API_KEY": cognee_cfg.api_key,
        "DATA_ROOT_DIRECTORY": str(BACKEND_ROOT / "data" / "cognee" / "storage"),
        "SYSTEM_ROOT_DIRECTORY": str(BACKEND_ROOT / "data" / "cognee" / "system"),
    }

    if cognee_cfg.service_url:
        env_map["COGNEE_SERVICE_URL"] = cognee_cfg.service_url

    for key, value in env_map.items():
        if value:
            os.environ[key] = value


async def connect_cognee() -> str:
    """Connect to Cognee Cloud when COGNEE_SERVICE_URL is set; else run locally."""
    import cognee

    if settings.cognee.service_url:
        await cognee.serve(
            url=settings.cognee.service_url,
            api_key=settings.cognee.api_key,
        )
        return "cloud"

    log.info(
        "COGNEE_SERVICE_URL not set — running local Cognee with Groq + FastEmbed",
    )
    return "local"


async def run_smoke_test() -> None:
    configure_cognee_environment()
    mode = await connect_cognee()
    log.info("cognee smoke test starting", mode=mode, dataset=SMOKE_DATASET)

    import cognee
    from cognee.api.v1.search import SearchType

    try:
        log.info("step 1: remember()")
        remember_result = await cognee.remember(SMOKE_TEXT, dataset_name=SMOKE_DATASET)
        remember_status, remember_payload = await resolve_remember_result(remember_result)
        log.info("remember complete", status=remember_status, payload_type=type(remember_payload).__name__)

        log.info("step 2: cognify()")
        cognify_result = await cognee.cognify(datasets=SMOKE_DATASET)
        log.info("cognify complete", result_preview=str(cognify_result)[:300])

        log.info("step 3: recall()")
        results = await cognee.recall(
            "Who supplies semiconductor chips to Apple?",
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[SMOKE_DATASET],
        )

        if not results:
            raise RuntimeError("recall() returned empty results")

        print("\n=== recall() results ===")
        for index, item in enumerate(results, start=1):
            print(f"{index}. {format_recall_item(item)}")

        log.info("cognee smoke test passed", result_count=len(results))
    finally:
        await cognee.disconnect()


def main() -> None:
    try:
        asyncio.run(run_smoke_test())
    except Exception:
        log.exception("cognee smoke test failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
