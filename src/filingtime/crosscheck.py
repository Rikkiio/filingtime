"""Compare parsed source facts with the SEC's separately extracted Companyfacts.

Agreement is an extraction cross-check, not an independent human accounting
label or evidence that this API is complete, historically frozen, or PIT-safe.
"""

from __future__ import annotations

import json
import re
import hashlib
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .ingest import load_jsonl, read_source
from .models import load_facts


def crosscheck_companyfacts(root: str | Path, split: str, *, write: bool = True) -> dict:
    root = Path(root)
    if split not in {"development", "holdout"}:
        raise ValueError("Unknown split")
    # Do not inspect held-out values through a different data product before freeze.
    if split == "holdout":
        from .freeze import check_freeze
        if check_freeze(root)["status"] != "unchanged":
            raise ValueError("Held-out cross-check requires unchanged frozen rules")
    sources = load_jsonl(root / "data/manifests/sources.jsonl")
    by_cik = {}
    for record in sources:
        if "/companyfacts/CIK" in record["url"]:
            cik = record["url"].split("/CIK")[-1].split(".")[0]
            by_cik[cik] = record
    cache = {}
    facts = [fact for fact in load_facts(root / f"data/processed/{split}_facts.jsonl") if fact.status == "accepted"]
    unique = {}
    for fact in facts:
        key = (fact.cik, fact.accession, fact.concept_namespace, fact.concept,
               fact.period_start, fact.period_end, fact.dimensions, fact.unit, fact.value)
        unique.setdefault(key, fact)
    rows = []
    for key, fact in sorted(unique.items()):
        source = by_cik.get(fact.cik)
        values = []
        if source is None:
            status = "no_companyfacts_snapshot"
        elif not re.fullmatch(r"https?://fasb\.org/us-gaap/\d{4}(?:-\d{2}-\d{2})?", fact.concept_namespace):
            status = "extension_not_covered_by_api"
        elif not fact.is_consolidated:
            status = "dimensional_fact_not_covered_by_api"
        else:
            if fact.cik not in cache:
                cache[fact.cik] = json.loads(read_source(root, source), parse_float=Decimal)
            if str(cache[fact.cik].get("cik", "")).zfill(10) != fact.cik:
                status = "snapshot_entity_mismatch"
                rows.append({"cik": fact.cik, "accession": fact.accession, "concept": fact.concept,
                             "concept_namespace": fact.concept_namespace,
                             "period_start": fact.period_start, "period_end": fact.period_end, "unit": fact.unit,
                             "raw_filing_value": fact.value, "sec_extracted_values": [], "status": status,
                             "original_source_url": fact.source_url, "comparison_source_url": source["url"],
                             "comparison_snapshot_sha256": source["sha256"]})
                continue
            local = fact.concept.split(":")[-1]
            concept = cache[fact.cik].get("facts", {}).get("us-gaap", {}).get(local, {})
            matches = [record for record in concept.get("units", {}).get(fact.unit, [])
                       if record.get("accn") == fact.accession and record.get("start") == fact.period_start
                       and record.get("end") == fact.period_end]
            values = sorted({format(Decimal(record["val"]), "f") for record in matches})
            if not values:
                status = "no_exact_accession_period_match"
            elif len({Decimal(value) for value in values}) > 1:
                status = "api_conflicting_values"
            elif Decimal(values[0]) == fact.number:
                status = "exact_match"
            else:
                status = "numeric_mismatch"
        rows.append({"cik": fact.cik, "accession": fact.accession, "concept": fact.concept,
                     "concept_namespace": fact.concept_namespace,
                     "period_start": fact.period_start, "period_end": fact.period_end, "unit": fact.unit,
                     "raw_filing_value": fact.value, "sec_extracted_values": values, "status": status,
                     "original_source_url": fact.source_url,
                     "comparison_source_url": source["url"] if source else None,
                     "comparison_snapshot_sha256": source["sha256"] if source else None})
    counts = Counter(row["status"] for row in rows)
    comparable = counts["exact_match"] + counts["numeric_mismatch"]
    summary = {"split": split, "unique_accepted_facts": len(rows), "status_counts": dict(sorted(counts.items())),
               "input_facts_sha256": hashlib.sha256((root / f"data/processed/{split}_facts.jsonl").read_bytes()).hexdigest(),
               "comparable_count": comparable, "exact_match_count": counts["exact_match"],
               "extraction_agreement": counts["exact_match"] / comparable if comparable else None,
               "source_fact_count_before_deduplication": len(facts),
               "human_review_status": "pending",
               "limitations": ["Companyfacts is a separate extraction path over the same issuer disclosures, not independent economic truth.",
                               "The current downloaded snapshot is not a historical API snapshot and never supplies PIT query values.",
                               "Custom-taxonomy facts and unmatched accession/period keys remain in the denominator ledger; no silent exclusion."]}
    if write:
        out = root / "data/results"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{split}_companyfacts_crosscheck.json").write_text(
            json.dumps({"summary": summary, "observations": rows}, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary
