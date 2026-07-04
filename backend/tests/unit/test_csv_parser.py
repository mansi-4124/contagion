"""
D2-10 — Unit tests for ERP CSV parser, written before implementation (TDD).

parse_erp_csv(file_bytes) validates the required columns
[supplier, component, volume_usd, country], cleans whitespace, and returns
a list of ERPRow. Missing required columns -> CSVValidationError, not a
silent partial parse — a company's onboarding data is exactly the kind of
input where "parse what you can" would silently produce a wrong graph.
"""

import pytest

from app.ingestion.csv_parser import CSVValidationError, ERPRow, parse_erp_csv


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


VALID_CSV = _csv_bytes(
    "supplier,component,volume_usd,country\n"
    "TSMC,A17 Bionic Chip,18000000000,Taiwan\n"
    "Foxconn,Final Assembly,9500000000,Taiwan\n"
)


class TestParseValidCsv:
    def test_returns_list_of_erp_row(self):
        rows = parse_erp_csv(VALID_CSV)
        assert len(rows) == 2
        assert all(isinstance(r, ERPRow) for r in rows)

    def test_parses_fields_correctly(self):
        rows = parse_erp_csv(VALID_CSV)
        assert rows[0].supplier == "TSMC"
        assert rows[0].component == "A17 Bionic Chip"
        assert rows[0].volume_usd == 18_000_000_000.0
        assert rows[0].country == "Taiwan"

    def test_volume_usd_is_float_type(self):
        rows = parse_erp_csv(VALID_CSV)
        assert isinstance(rows[0].volume_usd, float)

    def test_handles_columns_in_different_order(self):
        csv = _csv_bytes(
            "country,supplier,volume_usd,component\n"
            "Taiwan,TSMC,18000000000,A17 Bionic Chip\n"
        )
        rows = parse_erp_csv(csv)
        assert rows[0].supplier == "TSMC"
        assert rows[0].country == "Taiwan"


class TestWhitespaceCleaning:
    def test_strips_whitespace_from_string_fields(self):
        csv = _csv_bytes(
            "supplier,component,volume_usd,country\n"
            "  TSMC  , A17 Bionic Chip ,18000000000,  Taiwan  \n"
        )
        rows = parse_erp_csv(csv)
        assert rows[0].supplier == "TSMC"
        assert rows[0].component == "A17 Bionic Chip"
        assert rows[0].country == "Taiwan"

    def test_strips_whitespace_from_header_names(self):
        csv = _csv_bytes(
            " supplier , component , volume_usd , country \n"
            "TSMC,A17 Bionic Chip,18000000000,Taiwan\n"
        )
        rows = parse_erp_csv(csv)
        assert len(rows) == 1
        assert rows[0].supplier == "TSMC"

    def test_strips_commas_and_whitespace_from_volume_usd(self):
        """Real-world ERP exports often format numbers with thousands
        separators (e.g. Excel's default number format)."""
        csv = _csv_bytes(
            "supplier,component,volume_usd,country\n"
            "TSMC,A17 Bionic Chip, 18,000,000,000 ,Taiwan\n"
        )
        # Note: this row has an extra comma inside a quoted-less numeric
        # field, which is genuinely ambiguous for a CSV parser without
        # quotes. Use the quoted form instead:
        csv_quoted = _csv_bytes(
            'supplier,component,volume_usd,country\n'
            'TSMC,A17 Bionic Chip,"18,000,000,000",Taiwan\n'
        )
        rows = parse_erp_csv(csv_quoted)
        assert rows[0].volume_usd == 18_000_000_000.0


class TestCaseInsensitiveHeaders:
    def test_accepts_uppercase_headers(self):
        csv = _csv_bytes(
            "SUPPLIER,COMPONENT,VOLUME_USD,COUNTRY\n"
            "TSMC,A17 Bionic Chip,18000000000,Taiwan\n"
        )
        rows = parse_erp_csv(csv)
        assert rows[0].supplier == "TSMC"

    def test_accepts_mixed_case_headers(self):
        csv = _csv_bytes(
            "Supplier,Component,Volume_USD,Country\n"
            "TSMC,A17 Bionic Chip,18000000000,Taiwan\n"
        )
        rows = parse_erp_csv(csv)
        assert rows[0].supplier == "TSMC"


class TestMissingColumnValidation:
    def test_missing_country_column_raises_validation_error(self):
        """Direct restatement of D2-10's Done When."""
        csv = _csv_bytes(
            "supplier,component,volume_usd\n"
            "TSMC,A17 Bionic Chip,18000000000\n"
        )
        with pytest.raises(CSVValidationError) as exc_info:
            parse_erp_csv(csv)
        assert "country" in str(exc_info.value).lower()

    def test_missing_multiple_columns_lists_all_of_them(self):
        csv = _csv_bytes("supplier,component\nTSMC,A17 Bionic Chip\n")
        with pytest.raises(CSVValidationError) as exc_info:
            parse_erp_csv(csv)
        message = str(exc_info.value).lower()
        assert "volume_usd" in message
        assert "country" in message

    def test_empty_file_raises_validation_error(self):
        with pytest.raises(CSVValidationError):
            parse_erp_csv(b"")

    def test_header_only_no_data_rows_returns_empty_list_not_error(self):
        """A CSV with valid headers but zero data rows isn't a validation
        failure — it's just an empty upload."""
        csv = _csv_bytes("supplier,component,volume_usd,country\n")
        rows = parse_erp_csv(csv)
        assert rows == []


class TestRowLevelValidation:
    def test_non_numeric_volume_usd_raises_validation_error(self):
        csv = _csv_bytes(
            "supplier,component,volume_usd,country\n"
            "TSMC,A17 Bionic Chip,not-a-number,Taiwan\n"
        )
        with pytest.raises(CSVValidationError) as exc_info:
            parse_erp_csv(csv)
        message = str(exc_info.value).lower()
        assert "volume_usd" in message
        assert "row 2" in message or "row 1" in message  # 1-indexed data rows, either convention is fine as long as it's present

    def test_blank_supplier_raises_validation_error(self):
        csv = _csv_bytes(
            "supplier,component,volume_usd,country\n"
            ",A17 Bionic Chip,18000000000,Taiwan\n"
        )
        with pytest.raises(CSVValidationError) as exc_info:
            parse_erp_csv(csv)
        assert "supplier" in str(exc_info.value).lower()

    def test_skips_fully_blank_rows(self):
        csv = _csv_bytes(
            "supplier,component,volume_usd,country\n"
            "TSMC,A17 Bionic Chip,18000000000,Taiwan\n"
            ",,,\n"
            "Foxconn,Final Assembly,9500000000,Taiwan\n"
        )
        rows = parse_erp_csv(csv)
        assert len(rows) == 2
        assert rows[1].supplier == "Foxconn"

    def test_negative_volume_usd_raises_validation_error(self):
        csv = _csv_bytes(
            "supplier,component,volume_usd,country\n"
            "TSMC,A17 Bionic Chip,-500,Taiwan\n"
        )
        with pytest.raises(CSVValidationError):
            parse_erp_csv(csv)


class TestEncodingHandling:
    def test_handles_utf8_bom(self):
        """Excel commonly exports CSVs with a UTF-8 BOM prefix — a frequent
        real-world gotcha that silently corrupts the first header name if
        not stripped."""
        csv_with_bom = b"\xef\xbb\xbf" + VALID_CSV
        rows = parse_erp_csv(csv_with_bom)
        assert len(rows) == 2
        assert rows[0].supplier == "TSMC"