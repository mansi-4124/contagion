"""
Unit tests for app.ingestion.edgar.extractor (D2-02).

app.utils.llm.GroqClient is mocked throughout -- no real Groq calls here.
The one test that hits real Groq against real Apple 10-K text (matching
D2-02's literal "Done When": at least 5 named suppliers including TSMC)
lives in tests/integration/ingestion/edgar/test_extractor_integration.py.
"""
import json
from unittest.mock import AsyncMock

import pytest

from app.ingestion.edgar.extractor import (
    ExtractedSupplier,
    ExtractionParseError,
    extract_suppliers_from_text,
    _extract_relevant_excerpts,
)

VALID_SUPPLIER_JSON = json.dumps(
    [
        {
            "supplier_name": "TSMC",
            "component_supplied": "A-series and M-series chips",
            "country": "Taiwan",
            "exclusivity": "sole",
            "risk_notes": "Sole source for advanced-node silicon; concentrated in Hsinchu.",
        },
        {
            "supplier_name": "Samsung",
            "component_supplied": "OLED displays",
            "country": "South Korea",
            "exclusivity": "primary",
            "risk_notes": "Also a competitor in consumer electronics.",
        },
        {
            "supplier_name": "Foxconn",
            "component_supplied": "Final assembly",
            "country": "China",
            "exclusivity": "primary",
            "risk_notes": None,
        },
        {
            "supplier_name": "Qualcomm",
            "component_supplied": "Modem chips",
            "country": "United States",
            "exclusivity": "secondary",
            "risk_notes": None,
        },
        {
            "supplier_name": "Skyworks Solutions",
            "component_supplied": "RF components",
            "country": "United States",
            "exclusivity": None,
            "risk_notes": None,
        },
    ]
)


def make_mock_llm(response_text: str):
    llm = AsyncMock()
    llm.call_extraction = AsyncMock(return_value=response_text)
    return llm


class TestExtractSuppliersFromText:
    @pytest.mark.asyncio
    async def test_parses_valid_json_array_into_extracted_supplier_models(self):
        llm = make_mock_llm(VALID_SUPPLIER_JSON)

        suppliers = await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

        assert len(suppliers) == 5
        assert all(isinstance(s, ExtractedSupplier) for s in suppliers)
        names = [s.supplier_name for s in suppliers]
        assert "TSMC" in names

    @pytest.mark.asyncio
    async def test_passes_company_name_and_text_into_the_prompt(self):
        llm = make_mock_llm(VALID_SUPPLIER_JSON)

        await extract_suppliers_from_text("NVIDIA sources chips from TSMC.", "NVIDIA Corporation.", llm=llm)

        sent_prompt = llm.call_extraction.call_args[0][0]
        assert "NVIDIA Corporation." in sent_prompt
        assert "NVIDIA sources chips from TSMC." in sent_prompt

    @pytest.mark.asyncio
    async def test_strips_markdown_code_fences_before_parsing(self):
        fenced = f"```json\n{VALID_SUPPLIER_JSON}\n```"
        llm = make_mock_llm(fenced)

        suppliers = await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

        assert len(suppliers) == 5

    @pytest.mark.asyncio
    async def test_skips_malformed_entries_but_keeps_valid_ones(self):
        mixed = json.dumps(
            [
                {"supplier_name": "TSMC", "component_supplied": "Chips", "country": "Taiwan"},
                {"component_supplied": "Missing the required supplier_name field"},
            ]
        )
        llm = make_mock_llm(mixed)

        suppliers = await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

        assert len(suppliers) == 1
        assert suppliers[0].supplier_name == "TSMC"

    @pytest.mark.asyncio
    async def test_raises_extraction_parse_error_on_non_json_response(self):
        llm = make_mock_llm("I'm sorry, I can't help with that request.")

        with pytest.raises(ExtractionParseError):
            await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

    @pytest.mark.asyncio
    async def test_raises_extraction_parse_error_when_response_is_json_but_not_a_list(self):
        # A dict with no list-valued keys at all -- nothing to unwrap.
        llm = make_mock_llm(json.dumps({"supplier_name": "TSMC"}))

        with pytest.raises(ExtractionParseError):
            await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

    @pytest.mark.asyncio
    async def test_unwraps_single_key_object_wrapping_a_supplier_array(self):
        # Groq's json_object response_format can't return a bare top-level
        # array -- it wraps one under a key, e.g. {"data": [...]}. This is
        # the exact real shape Groq returned in production.
        wrapped = json.dumps({"data": json.loads(VALID_SUPPLIER_JSON)})
        llm = make_mock_llm(wrapped)

        suppliers = await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

        assert len(suppliers) == 5
        assert any(s.supplier_name == "TSMC" for s in suppliers)

    @pytest.mark.asyncio
    async def test_unwraps_regardless_of_key_name(self):
        # The unwrap logic doesn't care whether the key is "data", "suppliers",
        # "results", etc. -- only that there's exactly one list-valued key.
        wrapped = json.dumps({"suppliers": json.loads(VALID_SUPPLIER_JSON)})
        llm = make_mock_llm(wrapped)

        suppliers = await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

        assert len(suppliers) == 5

    @pytest.mark.asyncio
    async def test_raises_when_object_has_multiple_list_valued_keys(self):
        # Ambiguous -- can't guess which list is the supplier list, so this
        # must raise rather than silently picking one.
        ambiguous = json.dumps({"suppliers": [{"a": 1}], "sources": [{"b": 2}]})
        llm = make_mock_llm(ambiguous)

        with pytest.raises(ExtractionParseError):
            await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

    @pytest.mark.asyncio
    async def test_raises_when_object_has_no_list_valued_keys(self):
        no_list = json.dumps({"message": "no suppliers found", "count": 0})
        llm = make_mock_llm(no_list)

        with pytest.raises(ExtractionParseError):
            await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_model_returns_empty_array(self):
        llm = make_mock_llm("[]")

        suppliers = await extract_suppliers_from_text("filing text ...", "NVIDIA Corporation.", llm=llm)

        assert suppliers == []

    @pytest.mark.asyncio
    async def test_truncates_very_long_filing_text_before_building_prompt(self):
        long_text = "NVIDIA sources chips from TSMC. " * 5000  # far longer than the prompt budget
        llm = make_mock_llm(VALID_SUPPLIER_JSON)

        await extract_suppliers_from_text(long_text, "NVIDIA Corporation.", llm=llm)

        sent_prompt = llm.call_extraction.call_args[0][0]
        # the prompt shouldn't just dump the entire 160k-char string in verbatim
        assert len(sent_prompt) < len(long_text)


class TestExtractRelevantExcerpts:
    def test_finds_content_near_a_keyword_far_into_a_long_document(self):
        # This is the exact bug from production: a 50,000-char filing where
        # the supplier language is buried past char 20,000, but naive
        # text[:5000] truncation only ever sees cover-page boilerplate.
        boilerplate = "SEC cover page filler text. " * 800  # ~24,000 chars, no keyword
        relevant = "We rely on TSMC as a sole source supplier for advanced chips."
        more_boilerplate = "More filler text after the relevant part. " * 500
        long_filing = boilerplate + relevant + more_boilerplate

        excerpt = _extract_relevant_excerpts(long_filing, max_total_chars=2000)

        assert "TSMC" in excerpt
        assert "sole source" in excerpt

    def test_falls_back_to_document_head_when_no_keywords_found(self):
        no_keyword_text = "This filing discusses financial results only. " * 200

        excerpt = _extract_relevant_excerpts(no_keyword_text, max_total_chars=500)

        assert excerpt == no_keyword_text[:500]

    def test_merges_overlapping_windows_around_nearby_keywords(self):
        text = "prefix " * 50 + "sole source supplier and single source vendor" + " suffix" * 50
        excerpt = _extract_relevant_excerpts(text, max_total_chars=5000, window=200)
        # both keywords are close together -- should produce one merged
        # excerpt, not two separately-truncated overlapping copies
        assert excerpt.count("sole source") == 1
        assert excerpt.count("single source") == 1

    def test_respects_max_total_chars_budget(self):
        text = ("supplier concentration risk. " * 2000)  # many keyword hits
        excerpt = _extract_relevant_excerpts(text, max_total_chars=3000)
        assert len(excerpt) <= 3000

    def test_captures_multiple_distant_keyword_occurrences(self):
        text = (
            "irrelevant content " * 500
            + "TSMC is our sole source foundry."
            + "filler " * 500
            + "Samsung is a single source supplier of memory."
            + "filler " * 500
        )
        excerpt = _extract_relevant_excerpts(text, max_total_chars=10_000)
        assert "TSMC" in excerpt
        assert "Samsung" in excerpt


class TestExtractedSupplierModel:
    def test_optional_fields_default_to_none(self):
        supplier = ExtractedSupplier(supplier_name="TSMC", component_supplied="Chips", country="Taiwan")
        assert supplier.exclusivity is None
        assert supplier.risk_notes is None

    def test_requires_supplier_name_and_component_supplied(self):
        with pytest.raises(Exception):  # pydantic.ValidationError
            ExtractedSupplier(country="Taiwan")