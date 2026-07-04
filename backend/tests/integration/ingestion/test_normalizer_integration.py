"""
Integration test for app.ingestion.edgar.normalizer (D2-03) -- hits real Groq.

This is the literal "Done When" check from the task plan:
"normalize_company_name('TSMC') and normalize_company_name('Taiwan Semiconductor')
map to same canonical name"

Note the inherent risk this test carries: 'TSMC' and 'Taiwan Semiconductor'
are different cache keys, looked up independently (see normalizer.py's
module docstring) -- this test is really asserting that Groq's world
knowledge is consistent enough to answer both the same way, not that our
code forces them to match. If this becomes flaky in practice, the fix is a
small deterministic alias seed table for known demo companies, not more
prompt tweaking.

Run separately from the unit suite:
    pytest tests/integration -m integration
"""
import pytest

from app.ingestion.edgar.normalizer import normalize_company_name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tsmc_and_taiwan_semiconductor_converge_on_same_canonical_name():
    canonical_a = await normalize_company_name("TSMC")
    canonical_b = await normalize_company_name("Taiwan Semiconductor")

    assert canonical_a.strip().lower() == canonical_b.strip().lower()