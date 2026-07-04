"""
Hardcoded lookup from 6-digit Harmonized System (HS) trade codes to
human-readable component category names. Used by
app.ingestion.importyeti.client (D2-05) to translate raw customs/shipment
HS codes into the categories the graph's Component nodes use.

These are real HS 2022 nomenclature codes (not made up), chosen to cover the
supply-chain categories relevant to the demo companies (Apple, Tesla, Nvidia,
Pfizer, Ford): semiconductors, batteries, pharmaceuticals, EVs, rare earths,
displays, and raw/structural materials. Real ImportYeti data will include
HS codes outside this list -- hs_code_to_category() falls back to
"uncategorized" rather than raising, so an unrecognized code doesn't crash
the ingestion pipeline.
"""

HS_CODE_CATEGORIES: dict[int, str] = {
    # Semiconductors & fabrication equipment
    854231: "semiconductor_chips",
    854232: "memory_chips",
    854239: "other_semiconductors",
    848620: "semiconductor_equipment",
    854140: "leds_solar_cells",
    # Batteries
    850760: "lithium_batteries",
    850750: "nimh_batteries",
    850780: "other_batteries",
    # Pharmaceuticals
    300490: "pharmaceutical_apis",
    293399: "pharma_intermediates",
    300220: "vaccines",
    # Rare earth / critical minerals
    284690: "rare_earth_compounds",
    280530: "rare_earth_metals",
    # Consumer electronics / devices
    851712: "smartphones",
    847130: "laptops",
    852580: "camera_modules",
    852410: "display_panels",
    847330: "computer_parts",
    # Automotive
    870380: "electric_vehicles",
    840999: "engine_parts",
    848590: "machine_parts",
    700910: "automotive_glass",
    # Electrical / PCB components
    853400: "printed_circuit_boards",
    854442: "wiring_connectors",
    853650: "electrical_switches",
    853890: "electrical_parts",
    # Raw / structural materials
    760110: "aluminum_raw",
    720610: "steel_raw",
    392690: "plastic_components",
    # Lab / analytical
    902780: "lab_instruments",
}

UNCATEGORIZED = "uncategorized"


def hs_code_to_category(hs_code: int | str) -> str:
    """
    Look up the component category for an HS code. Accepts int or string
    input (ImportYeti's scraped HTML hands this function strings), with
    surrounding whitespace tolerated. Unknown codes return "uncategorized"
    rather than raising, so one unrecognized code doesn't halt ingestion for
    an entire company. Raises ValueError only if the input isn't a valid
    integer at all (e.g. non-numeric garbage).
    """
    try:
        normalized_code = int(str(hs_code).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid HS code: {hs_code!r}") from exc

    return HS_CODE_CATEGORIES.get(normalized_code, UNCATEGORIZED)