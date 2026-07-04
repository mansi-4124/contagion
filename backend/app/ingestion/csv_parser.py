"""
D2-10 — ERP CSV parser
File: backend/app/ingestion/csv_parser.py

parse_erp_csv(file_bytes) validates the required columns
[supplier, component, volume_usd, country], cleans whitespace, and returns
a list of ERPRow. Used by onboarding_service (D3) when a company uploads
their direct-supplier CSV (UC-01 step 2).

Design choice: missing required columns OR any row-level parse failure
(non-numeric volume_usd, blank required field) raises CSVValidationError
for the WHOLE file, rather than silently skipping bad rows. An onboarding
CSV becomes permanent graph structure (Company/Component nodes,
Architecture Spec §6.1) — a silently-dropped row here is a silently wrong
supply chain graph, which is worse than making the user fix their CSV and
re-upload.
"""

import csv
import io
from dataclasses import dataclass

REQUIRED_COLUMNS = ("supplier", "component", "volume_usd", "country")


class CSVValidationError(Exception):
    """Raised when the CSV is missing required columns or contains
    unparseable/invalid data in a required field."""


@dataclass(frozen=True)
class ERPRow:
    supplier: str
    component: str
    volume_usd: float
    country: str


def _normalize_header(name: str) -> str:
    return name.strip().lower()


def parse_erp_csv(file_bytes: bytes) -> list[ERPRow]:
    if not file_bytes:
        raise CSVValidationError("CSV file is empty.")

    # Strip UTF-8 BOM if present (common in Excel-exported CSVs) before
    # decoding, otherwise it corrupts the first header name.
    text = file_bytes.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise CSVValidationError("CSV file has no header row.")

    # Map normalized header name -> original header name, so we can look up
    # values by our normalized required-column names regardless of the
    # CSV's actual casing/whitespace.
    header_map = {_normalize_header(h): h for h in reader.fieldnames}

    missing = [col for col in REQUIRED_COLUMNS if col not in header_map]
    if missing:
        raise CSVValidationError(
            f"CSV is missing required column(s): {', '.join(missing)}. "
            f"Required columns are: {', '.join(REQUIRED_COLUMNS)}."
        )

    rows: list[ERPRow] = []
    for row_number, raw_row in enumerate(reader, start=1):
        values = {col: (raw_row.get(header_map[col]) or "").strip() for col in REQUIRED_COLUMNS}

        # Skip fully blank rows (common trailing artifact in exported CSVs)
        if not any(values.values()):
            continue

        for col in ("supplier", "component", "country"):
            if not values[col]:
                raise CSVValidationError(f"Row {row_number}: '{col}' is required but blank.")

        raw_volume = values["volume_usd"].replace(",", "").replace("$", "")
        try:
            volume_usd = float(raw_volume)
        except ValueError as e:
            raise CSVValidationError(
                f"Row {row_number}: 'volume_usd' value {values['volume_usd']!r} is not a valid number."
            ) from e

        if volume_usd < 0:
            raise CSVValidationError(f"Row {row_number}: 'volume_usd' cannot be negative ({volume_usd}).")

        rows.append(ERPRow(
            supplier=values["supplier"],
            component=values["component"],
            volume_usd=volume_usd,
            country=values["country"],
        ))

    return rows