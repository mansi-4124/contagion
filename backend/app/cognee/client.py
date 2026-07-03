from dataclasses import dataclass
from enum import Enum
from typing import Any

import cognee

from app.config.settings import settings

_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return

    cognee.config.set_llm_config({
        "llm_provider": "groq",
        "llm_api_key": settings.llm.groq_api_key,
        "llm_model": settings.llm.synthesis_model,
    })
    cognee.config.set_embedding_config({
        "embedding_provider": settings.embedding.provider,  # "fastembed"
        "embedding_model": settings.embedding.model_name,
    })
    # Cognee Cloud auth — adjust if the SDK exposes a dedicated cloud config call;
    # some versions read COGNEE_API_KEY from env directly instead of a setter.
    import os
    os.environ.setdefault("COGNEE_API_KEY", settings.cognee.api_key)

    _configured = True


class SearchType(str, Enum):
    GRAPH_COMPLETION = "GRAPH_COMPLETION"
    CHUNKS = "CHUNKS"
    SUMMARIES = "SUMMARIES"


@dataclass(frozen=True)
class CognifyResult:
    nodes_created: int
    edges_created: int


@dataclass(frozen=True)
class RecallResult:
    raw: Any
    text: str


async def remember(dataset_name: str, text: str) -> None:
    _ensure_configured()
    await cognee.add(text, dataset_name=dataset_name)


async def cognify(dataset_name: str) -> CognifyResult:
    _ensure_configured()
    result = await cognee.cognify(dataset_name=dataset_name)
    # Shape of `result` depends on SDK version — adjust extraction once verified
    # against your installed cognee version's actual return value.
    nodes = getattr(result, "nodes_created", 0) or 0
    edges = getattr(result, "edges_created", 0) or 0
    return CognifyResult(nodes_created=nodes, edges_created=edges)


async def recall(dataset_name: str, query: str, search_type: SearchType = SearchType.GRAPH_COMPLETION) -> RecallResult:
    _ensure_configured()
    raw = await cognee.search(query, dataset_name=dataset_name, search_type=search_type.value)
    text = raw if isinstance(raw, str) else str(raw)
    return RecallResult(raw=raw, text=text)


async def improve(dataset_name: str, edge_ref: dict, weight_delta: float) -> None:
    _ensure_configured()
    # Cognee's edge-weight update API — wire up once confirmed against SDK docs
    # for your Cognee Cloud version. Left as an explicit TODO rather than a
    # silent no-op so it doesn't get missed.
    raise NotImplementedError("improve() — confirm Cognee Cloud edge-update API before D3")


async def forget(dataset_name: str, node_ref: dict, reason: str) -> dict:
    _ensure_configured()
    raise NotImplementedError("forget() — confirm Cognee Cloud node-deletion API before use")