"""
D2-11 smoke test — real call against Groq, not mocked.
Done When: prints a non-empty string extracted from the sample sentence.
"""
import asyncio

from app.utils.llm import GroqClient


async def main():
    client = GroqClient()
    result = await client.call_extraction(
        "Extract suppliers from: Apple buys chips from TSMC. "
        'Return JSON as {"suppliers": [string]}.'
    )
    assert result and len(result) > 0, "call_extraction returned empty string"
    print("call_extraction() output:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())