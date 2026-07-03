"""
D0-07 (revised for Cognee 1.2.2 real API) — Cognee smoke test
File: backend/scripts/cognee_smoke_test.py

Verifies Groq (LLM) + FastEmbed (embeddings) + Cognee are all wired
correctly, end to end: remember() -> cognify() -> recall().

Done When: script prints a non-empty recall() result. No import errors.

Run:
    python scripts/cognee_smoke_test.py
"""

import asyncio
import sys
import uuid

from app.cognee.client import remember, cognify, recall, SearchType
from app.config.settings import settings


TEST_DATASET = f"smoke_test_{uuid.uuid4().hex[:8]}"

TEST_TEXT = (
    "TSMC supplies the A17 Bionic chip to Apple from its Fab 18 facility in "
    "Tainan, Taiwan. Apple uses the A17 chip in the iPhone 16 Pro, which "
    "accounts for 28 percent of Apple's hardware revenue."
)


async def main() -> None:
    print(f"[1/4] Config check — LLM provider: {settings.llm.provider}, model: {settings.llm.model}")
    print(f"       Embedding provider: {settings.embedding.provider}, model: {settings.embedding.model}")
    print(f"       Cognee dataset (throwaway): {TEST_DATASET}")

    try:
        print("\n[2/4] remember() — ingesting test text...")
        await remember(TEST_DATASET, TEST_TEXT)
        print("       OK")

        print("\n[3/4] cognify() — building graph from ingested text...")
        cognify_result = await cognify(TEST_DATASET)
        print(f"       OK — status={cognify_result.status}, dataset_name={cognify_result.dataset_name}")
        print(f"       pipeline_run_id={cognify_result.pipeline_run_id}")

        print("\n[4/4] recall() — querying the graph...")
        result = await recall(
            TEST_DATASET,
            "Who supplies chips to Apple?",
            search_type=SearchType.GRAPH_COMPLETION,
        )
        print(f"       OK — result:\n\n{result.text}\n")

        if not result.text or not result.text.strip():
            print("[FAIL] recall() returned an empty result.", file=sys.stderr)
            sys.exit(1)

        if "tsmc" not in result.text.lower():
            print(
                "[WARN] recall() succeeded but didn't mention TSMC — graph may not "
                "have extracted the relationship correctly. Inspect the result above.",
            )

        print("[OK] Cognee + Groq + FastEmbed smoke test passed.")

    except Exception as e:
        print(f"\n[FAIL] Smoke test failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())