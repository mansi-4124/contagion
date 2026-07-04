"""
Unit tests for app.ingestion.importyeti.hs_codes (D2-04).

Pure static lookup, no mocking needed -- no LLM, no network.
"""
import pytest

from app.ingestion.importyeti.hs_codes import HS_CODE_CATEGORIES, hs_code_to_category


class TestLookupTableShape:
    def test_has_exactly_30_entries(self):
        # Literal task requirement: "hardcode lookup dict mapping 30 HS codes"
        assert len(HS_CODE_CATEGORIES) == 30

    def test_all_keys_are_six_digit_hs_codes(self):
        for code in HS_CODE_CATEGORIES:
            assert isinstance(code, int)
            assert 100000 <= code <= 999999, f"{code} is not a valid 6-digit HS code"

    def test_all_values_are_non_empty_snake_case_strings(self):
        for category in HS_CODE_CATEGORIES.values():
            assert isinstance(category, str) and category
            assert category == category.lower()
            assert " " not in category

    def test_keys_are_unique(self):
        # dict literal already guarantees this, but a duplicate category
        # VALUE mapped from two different codes is fine and expected --
        # this just documents that key collisions aren't possible here.
        assert len(HS_CODE_CATEGORIES) == len(set(HS_CODE_CATEGORIES.keys()))


class TestHsCodeToCategory:
    def test_known_code_returns_correct_category(self):
        # D2-04's literal Done-When check
        assert hs_code_to_category(854231) == "semiconductor_chips"

    def test_other_seed_examples_from_task_description(self):
        assert hs_code_to_category(850760) == "lithium_batteries"
        assert hs_code_to_category(300490) == "pharmaceutical_apis"

    def test_accepts_string_input(self):
        # ImportYeti's scraped HTML will hand this function strings, not ints
        assert hs_code_to_category("854231") == "semiconductor_chips"

    def test_accepts_string_input_with_surrounding_whitespace(self):
        assert hs_code_to_category(" 854231 ") == "semiconductor_chips"

    def test_unknown_code_returns_uncategorized_fallback(self):
        # Real-world ImportYeti data will include HS codes outside our
        # hardcoded 30 -- this must degrade gracefully, not crash the
        # ingestion pipeline.
        assert hs_code_to_category(999999) == "uncategorized"

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError):
            hs_code_to_category("not-a-code")