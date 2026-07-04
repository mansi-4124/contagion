"""
D2-12 — Seed data script
File: backend/scripts/seed_data.py

(... same docstring as before, with dataset-naming section replaced ...)

--- Dataset naming: deterministic UUIDs, not real company records --------
namespace_for(company_id) (app/cognee/datasets.py) expects a real UUID from
a `companies` table row (Architecture Spec §6.5) — but these 5 demo
companies don't have one yet at Day 2 (that's D3's onboarding_service).
Rather than duplicate onboarding logic here, or use an ad hoc slug that
diverges from the real naming scheme, each company gets a deterministic
UUID via uuid5(DEMO_NAMESPACE, company_name) — re-running this script
always regenerates the same UUID for "Apple", so remember() calls stay
idempotent to the same dataset across runs. The name->UUID mapping is
persisted to demo_company_ids.json so D2-14 (run_bootstrap.py) and D7
(trigger_demo_event.py) can resolve "Apple" -> its dataset without
re-deriving the UUID themselves.
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from app.cognee.client import remember
from app.cognee.datasets import namespace_for
from app.ingestion.comtrade.client import ComtradeUnavailableError, fetch_trade_volume
from app.ingestion.edgar.client import (
    CompanyNotFoundError,
    NoFilingFoundError,
    fetch_10k_filing_url,
    fetch_10k_text,
    fetch_company_cik,
)
from app.ingestion.edgar.extractor import ExtractionParseError, extract_suppliers_from_text
from app.ingestion.edgar.normalizer import normalize_company_name
from app.ingestion.gdelt.client import GdeltAPIError, fetch_supply_chain_news
from app.ingestion.importyeti.client import scrape_supplier_relationships
from app.ingestion.importyeti.hs_codes import hs_code_to_category
from app.ingestion.usgs.client import UsgsAPIError, fetch_significant_earthquakes
from app.utils.llm import GroqClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"

DEMO_COMPANIES = ["Apple", "Tesla", "Nvidia", "Pfizer", "Ford"]

# Fixed namespace so uuid5(DEMO_NAMESPACE, name) is stable across runs and
# across machines -- any valid UUID works here, this one is arbitrary but
# constant.
DEMO_NAMESPACE = uuid.UUID("6f8e1a2b-6b0e-4b8a-9b8e-2f6a1b3c4d5e")

COUNTRY_NAME_TO_UN_CODE = {
    "united states": "842",
    "taiwan": "158",
    "malaysia": "458",
    "south korea": "410",
    "china": "156",
    "japan": "392",
    "switzerland": "757",
    "germany": "276",
    "netherlands": "528",
}
US_REPORTER_CODE = COUNTRY_NAME_TO_UN_CODE["united states"]

INTER_COMPANY_DELAY_SECONDS = 1.0


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _demo_company_id(company_name: str) -> uuid.UUID:
    """Deterministic UUID for a demo company name — see module docstring."""
    return uuid.uuid5(DEMO_NAMESPACE, company_name.strip().lower())


def _save_json(filename: str, data: Any) -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    path = SEED_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("Wrote %s", path)


async def _seed_edgar(company_name: str, dataset_name: str, llm: GroqClient) -> list[dict]:
    try:
        cik = await fetch_company_cik(company_name)
        filing_url = await fetch_10k_filing_url(cik)
        filing_text = await fetch_10k_text(filing_url)
    except (CompanyNotFoundError, NoFilingFoundError) as e:
        logger.warning("EDGAR unavailable for %r: %s — skipping EDGAR step.", company_name, e)
        return []

    try:
        suppliers = await extract_suppliers_from_text(filing_text, company_name, llm=llm)
    except ExtractionParseError as e:
        logger.warning("EDGAR extraction failed for %r: %s — skipping EDGAR step.", company_name, e)
        return []

    normalized_records: list[dict] = []
    for supplier in suppliers:
        canonical_name = await normalize_company_name(supplier.supplier_name, llm=llm)
        record = supplier.model_dump()
        record["supplier_name"] = canonical_name
        record["source"] = "edgar_inferred"
        normalized_records.append(record)

        text = (
            f"{canonical_name} supplies {supplier.component_supplied} to {company_name}"
            f"{f' from {supplier.country}' if supplier.country else ''}. "
            f"Risk note: {supplier.risk_notes or 'none disclosed'}."
        )
        await remember(dataset_name, text)

    logger.info("EDGAR: %d supplier(s) extracted for %r", len(normalized_records), company_name)
    return normalized_records


async def _seed_importyeti(company_name: str, dataset_name: str) -> list[dict]:
    try:
        relationships = await scrape_supplier_relationships(company_name)
    except Exception as e:
        logger.warning("ImportYeti step failed unexpectedly for %r: %s", company_name, e)
        return []

    for rel in relationships:
        category = hs_code_to_category(rel["hs_code"]) if rel["hs_code"] else "uncategorized"
        text = (
            f"{rel['shipper_name']} supplies {category} to {company_name} "
            f"from {rel['country']}. Shipment frequency: {rel['shipment_count']} shipments."
        )
        await remember(dataset_name, text)

    logger.info("ImportYeti: %d relationship(s) found for %r", len(relationships), company_name)
    return relationships


async def _seed_comtrade(company_name: str, dataset_name: str, importyeti_records: list[dict]) -> list[dict]:
    seen_pairs: set[tuple[str, str]] = set()
    results: list[dict] = []

    for rel in importyeti_records:
        country_name = (rel.get("country") or "").strip().lower()
        hs_code = rel.get("hs_code") or ""
        if not country_name or not hs_code:
            continue

        partner_code = COUNTRY_NAME_TO_UN_CODE.get(country_name)
        if partner_code is None:
            logger.info("No UN country code mapping for %r — skipping Comtrade lookup.", country_name)
            continue

        pair_key = (partner_code, hs_code)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        try:
            trade = await fetch_trade_volume(US_REPORTER_CODE, partner_code, hs_code)
        except ComtradeUnavailableError as e:
            logger.info("No Comtrade data for %s: %s", pair_key, e)
            continue

        category = hs_code_to_category(hs_code)
        exporter_name = country_name.title()
        text = (
            f"{exporter_name} exports ${trade.trade_value_usd / 1e9:.2f}B of {category} "
            f"to United States annually (HS {hs_code})."
        )
        await remember(dataset_name, text)
        results.append({
            "trade_value_usd": trade.trade_value_usd,
            "year": trade.year,
            "reporter": trade.reporter,
            "partner": trade.partner,
            "hs_code": trade.hs_code,
            "source": trade.source,
        })

    logger.info("Comtrade: %d trade-volume record(s) found for %r", len(results), company_name)
    return results


def _merge_tier1(edgar_records: list[dict], importyeti_records: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for r in edgar_records:
        merged[r["supplier_name"].strip().lower()] = r
    for r in importyeti_records:
        key = r["shipper_name"].strip().lower()
        if key not in merged:
            merged[key] = {
                "supplier_name": r["shipper_name"],
                "component_supplied": hs_code_to_category(r["hs_code"]) if r["hs_code"] else "uncategorized",
                "country": r["country"],
                "exclusivity": None,
                "risk_notes": None,
                "source": "trade_inferred",
            }
    return list(merged.values())


async def _seed_company(company_name: str, llm: GroqClient) -> uuid.UUID:
    slug = _slugify(company_name)
    company_id = _demo_company_id(company_name)
    dataset_name = namespace_for(company_id)
    logger.info("=== Seeding %s (id=%s, dataset=%s) ===", company_name, company_id, dataset_name)

    edgar_records = await _seed_edgar(company_name, dataset_name, llm)
    importyeti_records = await _seed_importyeti(company_name, dataset_name)
    comtrade_records = await _seed_comtrade(company_name, dataset_name, importyeti_records)

    tier1_merged = _merge_tier1(edgar_records, importyeti_records)

    _save_json(f"{slug}_tier1.json", tier1_merged)
    _save_json(f"{slug}_importyeti.json", importyeti_records)
    _save_json(f"{slug}_comtrade.json", comtrade_records)

    return company_id


async def _seed_global_feeds() -> None:
    try:
        news = await fetch_supply_chain_news(timespan="30d")
    except GdeltAPIError as e:
        logger.warning("GDELT fetch failed: %s", e)
        news = []
    _save_json("gdelt_supply_chain_news.json", news)

    try:
        quakes = await fetch_significant_earthquakes(min_magnitude=4.0)
    except UsgsAPIError as e:
        logger.warning("USGS fetch failed: %s", e)
        quakes = []
    _save_json("usgs_earthquakes.json", quakes)


async def main() -> None:
    llm = GroqClient()

    await _seed_global_feeds()

    company_ids: dict[str, str] = {}
    for i, company_name in enumerate(DEMO_COMPANIES):
        company_id = await _seed_company(company_name, llm)
        company_ids[company_name] = str(company_id)
        if i < len(DEMO_COMPANIES) - 1:
            await asyncio.sleep(INTER_COMPANY_DELAY_SECONDS)

    _save_json("demo_company_ids.json", company_ids)
    logger.info("Seeding complete. Output written to %s", SEED_DIR)


if __name__ == "__main__":
    asyncio.run(main())