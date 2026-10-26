"""Download the preregistered source corpus; financial values are not parsed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from filingtime.ingest import SecCollector, append_jsonl, load_jsonl, read_universe, utc_now  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--tickers", help="Comma separated subset of the frozen universe")
    parser.add_argument("--split", choices=["development", "holdout"])
    parser.add_argument("--max-filings", type=int, help="Limit each issuer for an initial smoke check")
    parser.add_argument("--companyfacts", action="store_true", help="Also download SEC extracted facts for cross-check only")
    args = parser.parse_args()
    collector = SecCollector(args.root)
    universe = read_universe(args.root)
    if args.tickers:
        requested = set(args.tickers.upper().split(","))
        universe = [r for r in universe if r["ticker"] in requested]
        unknown = requested - {r["ticker"] for r in universe}
        if unknown:
            parser.error(f"Tickers outside frozen universe: {sorted(unknown)}")
    if args.split:
        universe = [r for r in universe if r["split"] == args.split]
    filings_path = args.root / "data/manifests/filings.jsonl"
    existing = {r["accession"] for r in load_jsonl(filings_path)}
    statuses = []
    for company in universe:
        metadata, filings = collector.company_filings(company["cik"])
        selection_file = args.root / "data/manifests" / f"selection_{company['cik']}.json"
        selection_file.write_text(json.dumps(collector.selection_audit[company["cik"]], indent=2) + "\n", encoding="utf-8")
        identity = {"cik": company["cik"], "sample_ticker": company["ticker"], "current_sec_name": metadata["name"], "current_sec_tickers": metadata.get("tickers", []), "checked_at": utc_now(), "note": "CIK is the stable identity; historical sample ticker need not remain listed"}
        identity_file = args.root / "data/manifests" / f"identity_{company['cik']}.json"
        if not identity_file.exists():
            identity_file.write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        selected = filings[:args.max_filings] if args.max_filings else filings
        for filing in selected:
            if filing["accessionNumber"] in existing:
                continue
            print(f"collect {company['ticker']} {filing['filingDate']} {filing['form']} {filing['accessionNumber']}", flush=True)
            record = collector.collect_filing(company, filing)
            append_jsonl(filings_path, record)
            existing.add(record["accession"])
        if args.companyfacts:
            cik = company["cik"]
            collector.fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", f"data/raw/{cik}/metadata/companyfacts.json.gz", "sec_extracted_crosscheck_not_ground_truth")
        statuses.append({"ticker": company["ticker"], "split": company["split"], "eligible_filings": len(filings), "downloaded_filings": sum(f["accessionNumber"] in existing for f in filings)})
        print(json.dumps(statuses[-1]), flush=True)
    output = {"completed_at": utc_now(), "selected_companies": statuses, "sources": len(collector.sources), "financial_values_inspected": False}
    print(json.dumps(output, indent=2), flush=True)
    (args.root / "data/manifests/collection_status.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
