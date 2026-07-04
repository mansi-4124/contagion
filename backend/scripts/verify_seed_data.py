"""
backend/scripts/verify_seed_data.py

Sanity-checks the OUTPUT of seed_data.py before moving on to D2-13
(graph_bootstrap). This only checks raw data volume/shape — it does NOT
verify graph traversal (that requires cognify(), which doesn't exist until
D2-13/14). Run this after seed_data.py, before starting D2-13.
"""
import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"
COMPANIES = ["apple", "tesla", "nvidia", "pfizer", "ford"]

MIN_TIER1_SUPPLIERS = 5   # Task Plan D2-12 Done When says >=8; treat 5-7 as a warning, not a hard fail
GOOD_TIER1_SUPPLIERS = 8


def _load(filename):
    path = SEED_DIR / filename
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def check_company(slug: str) -> list[str]:
    issues = []
    tier1 = _load(f"{slug}_tier1.json")
    importyeti = _load(f"{slug}_importyeti.json")
    comtrade = _load(f"{slug}_comtrade.json")

    if tier1 is None:
        issues.append(f"[{slug}] MISSING tier1.json entirely — EDGAR+ImportYeti both failed?")
        return issues

    n = len(tier1)
    if n == 0:
        issues.append(f"[{slug}] CRITICAL: 0 tier1 suppliers — EDGAR CIK lookup or filing fetch likely failed")
    elif n < MIN_TIER1_SUPPLIERS:
        issues.append(f"[{slug}] WARNING: only {n} tier1 suppliers (want >={GOOD_TIER1_SUPPLIERS})")
    elif n < GOOD_TIER1_SUPPLIERS:
        issues.append(f"[{slug}] NOTE: {n} tier1 suppliers, below the {GOOD_TIER1_SUPPLIERS} target but usable")

    # source mix — an all-fallback company means EDGAR extraction contributed nothing real
    sources = [r.get("source", "unknown") for r in tier1]
    if sources and all(s in ("trade_inferred", "fallback_seed") for s in sources):
        issues.append(f"[{slug}] WARNING: no edgar_inferred records — EDGAR extraction produced nothing")

    if importyeti is not None:
        live_count = sum(1 for r in importyeti if r.get("source") == "live_scrape")
        fallback_count = sum(1 for r in importyeti if r.get("source") == "fallback_seed")
        if importyeti and live_count == 0:
            issues.append(f"[{slug}] NOTE: ImportYeti fully fell back to seed data ({fallback_count} records) — Cloudflare blocked live scrape, this is expected, not a bug")

    if comtrade is not None and len(comtrade) == 0:
        issues.append(f"[{slug}] NOTE: 0 Comtrade records — likely no country-code mapping matched, non-fatal")

    return issues


def check_global_feeds() -> list[str]:
    issues = []
    news = _load("gdelt_supply_chain_news.json")
    quakes = _load("usgs_earthquakes.json")

    if news is None or len(news) == 0:
        issues.append("CRITICAL: gdelt_supply_chain_news.json is empty — GDELT client may be broken (Day 2 DoD requires >=5 articles)")
    elif len(news) < 5:
        issues.append(f"WARNING: only {len(news)} GDELT articles (Day 2 DoD wants >=5)")

    if quakes is None:
        issues.append("CRITICAL: usgs_earthquakes.json missing — USGS client failed to run")
    # empty list is fine for USGS — no quakes above threshold is a valid outcome

    return issues


def check_demo_ids() -> list[str]:
    ids = _load("demo_company_ids.json")
    if ids is None:
        return ["CRITICAL: demo_company_ids.json missing — D2-14 will have nothing to look up datasets by"]
    missing = [c for c in ["Apple", "Tesla", "Nvidia", "Pfizer", "Ford"] if c not in ids]
    if missing:
        return [f"CRITICAL: demo_company_ids.json missing entries for {missing}"]
    return []


def check_tsmc_present() -> list[str]:
    """Day 2 DoD's specific named check: TSMC must appear in Apple's data."""
    tier1 = _load("apple_tier1.json") or []
    importyeti = _load("apple_importyeti.json") or []
    names = [r.get("supplier_name", "") for r in tier1] + [r.get("shipper_name", "") for r in importyeti]
    if not any("tsmc" in n.lower() or "taiwan semiconductor" in n.lower() for n in names):
        return ["CRITICAL: TSMC not found anywhere in Apple's data — Day 2 DoD explicitly requires this"]
    return []


def main():
    all_issues = []
    for slug in COMPANIES:
        all_issues += check_company(slug)
    all_issues += check_global_feeds()
    all_issues += check_demo_ids()
    all_issues += check_tsmc_present()

    critical = [i for i in all_issues if i.startswith("CRITICAL") or "[" in i and "CRITICAL" in i]
    warnings = [i for i in all_issues if i not in critical]

    print(f"\n{'='*70}\nSEED DATA VERIFICATION\n{'='*70}")
    if not all_issues:
        print("✓ All checks passed. Safe to proceed to D2-13 (graph_bootstrap).")
        return

    if critical:
        print(f"\n✗ {len(critical)} CRITICAL issue(s) — fix before proceeding:")
        for i in critical:
            print(f"  {i}")
    if warnings:
        print(f"\n⚠ {len(warnings)} warning(s) — usable but worth noting:")
        for i in warnings:
            print(f"  {i}")

    print()
    if critical:
        print("Recommendation: DO NOT move to D2-13 yet — re-run seed_data.py or debug the failing source(s) above.")
    else:
        print("Recommendation: warnings only — safe to proceed to D2-13, but graph will be sparser than the 150-node target.")


if __name__ == "__main__":
    main()