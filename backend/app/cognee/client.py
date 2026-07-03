"""
D1-09 — Cognee client wrapper (Cognee 1.2.2, local or Cognee Cloud)
File: backend/app/cognee/client.py

Parameter names below were verified directly against the installed
cognee==1.2.2 source (not assumed from docs), since the library has no
`dataset_name` kwarg on cognify()/search() — only add() accepts it.
Passing the wrong kwarg to cognify()/search() doesn't error immediately;
cognify() swallows it into **kwargs and threads it all the way down into
the raw LLM completion request, which providers with strict schema
validation (Groq) then reject.
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Union

import litellm
import cognee
from cognee.modules.search.types import SearchType as _CogneeSearchType

from app.config.settings import settings

_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return

    # Defensive — harmless if the real leak (wrong kwarg name below) is fixed,
    # but cheap insurance against any other provider ever rejecting an unknown
    # top-level field LiteLLM forwards.
    litellm.drop_params = True

    os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

    model_name = settings.llm.model
    if not model_name.startswith("openai/"):
        model_name = f"openai/{model_name.removeprefix('groq/')}"

    cognee.config.set_llm_config({
        "llm_provider": "openai",
        "llm_model": model_name,
        "llm_api_key": settings.llm.api_key,
        "llm_endpoint": settings.llm.base_url,
    })

    cognee.config.set_embedding_config({
        "embedding_provider": settings.embedding.provider,
        "embedding_model": settings.embedding.model,
        "embedding_dimensions": settings.embedding.dimensions,
    })

    os.environ.setdefault("COGNEE_API_KEY", settings.cognee.api_key)
    if settings.cognee.service_url:
        os.environ.setdefault("COGNEE_SERVICE_URL", settings.cognee.service_url)

    _configured = True


class SearchType(str, Enum):
    """Facade over cognee's real SearchType enum — only exposing the subset
    the Architecture Spec §6.4 actually calls for. Mapped to the real enum
    in recall() below, since cognee.search()'s query_type param expects an
    actual SearchType member, not a plain string."""
    GRAPH_COMPLETION = "GRAPH_COMPLETION"
    CHUNKS = "CHUNKS"
    SUMMARIES = "SUMMARIES"


_SEARCH_TYPE_MAP = {
    SearchType.GRAPH_COMPLETION: _CogneeSearchType.GRAPH_COMPLETION,
    SearchType.CHUNKS: _CogneeSearchType.CHUNKS,
    SearchType.SUMMARIES: _CogneeSearchType.SUMMARIES,
}


@dataclass(frozen=True)
class CognifyResult:
    status: str
    pipeline_run_id: str
    dataset_name: str
    # NOTE: cognee 1.2.2's PipelineRunInfo does NOT return node/edge counts —
    # verified against the actual model (status, pipeline_run_id, dataset_id,
    # dataset_name, payload, data_ingestion_info only). If dataset_namespaces
    # .node_count/.edge_count (Architecture Spec §5.3) need real numbers,
    # get them via a follow-up recall() graph query after cognify() completes,
    # not from this return value. graph_bootstrap (D2-13) already plans a
    # validation recall() anyway — reuse that instead of parsing this result.


@dataclass(frozen=True)
class RecallResult:
    raw: Any
    text: str


async def remember(dataset_name: str, text: str) -> None:
    """add()'s real param IS `dataset_name` — this one was already correct."""
    _ensure_configured()
    await cognee.add(text, dataset_name=dataset_name)


async def cognify(dataset_name: str) -> CognifyResult:
    _ensure_configured()
    # Real param is `datasets` (str | list[str] | list[UUID]), NOT dataset_name.
    result = await cognee.cognify(datasets=dataset_name)

    # Blocking cognify() returns either a single PipelineRunInfo, or a
    # dict[dataset_id -> PipelineRunInfo] when multiple datasets are processed
    # (verified against run_pipeline_blocking). We pass a single dataset name,
    # but handle both shapes defensively.
    if isinstance(result, dict):
        run_info = next(iter(result.values())) if result else None
    else:
        run_info = result

    if run_info is None:
        return CognifyResult(status="unknown", pipeline_run_id="", dataset_name=dataset_name)

    return CognifyResult(
        status=getattr(run_info, "status", "unknown"),
        pipeline_run_id=str(getattr(run_info, "pipeline_run_id", "")),
        dataset_name=getattr(run_info, "dataset_name", dataset_name),
    )


async def recall(dataset_name: str, query: str, search_type: SearchType):
    _ensure_configured()

    results = await cognee.search(
        query_text=query,
        query_type=_SEARCH_TYPE_MAP[search_type],
        datasets=dataset_name,
    )

    if not results:
        return RecallResult(raw=results, text="")

    if isinstance(results, str):
        return RecallResult(raw=results, text=results)

    texts = []
    for r in results:
        if isinstance(r, str):
            texts.append(r)
        elif hasattr(r, "search_result"):
            texts.append(str(r.search_result))
        else:
            texts.append(str(r))

    return RecallResult(raw=results, text="\n\n".join(texts))


async def improve(dataset_name: str, edge_ref: dict, weight_delta: float) -> None:
    _ensure_configured()
    raise NotImplementedError(
        "improve() — cognee 1.2.2 exposes native remember/recall/forget/improve "
        "functions (per the startup log) that may map more directly than this "
        "wrapper's legacy add/cognify/search calls. Inspect cognee.improve()'s "
        "real signature before implementing this for D3."
    )


async def forget(dataset_name: str, node_ref: dict, reason: str) -> dict:
    _ensure_configured()
    raise NotImplementedError(
        "forget() — same note as improve(): check cognee.forget()'s real "
        "signature (native API) before implementing, rather than assuming."
    )