"""Checks that are independent of the economic interpretation of a fact."""

from __future__ import annotations

import gzip
import hashlib
import json
import csv
from collections import Counter
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_corpus(root: str | Path) -> dict:
    """Hash the actual archived bytes, not a producer's success flag."""
    root = Path(root).resolve()
    records = read_jsonl(root / "data/manifests/sources.jsonl")
    failures: list[dict] = []
    urls: dict[str, str] = {}
    total_bytes = 0
    for record in records:
        relative = record.get("local_path", "")
        path = (root / relative).resolve()
        error = None
        try:
            if not path.is_relative_to(root) or not relative:
                raise ValueError("source path escapes corpus")
            compressed = path.read_bytes()
            if hashlib.sha256(compressed).hexdigest() != record["compressed_sha256"]:
                raise ValueError("compressed hash mismatch")
            raw = gzip.decompress(compressed)
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError("raw hash mismatch")
            total_bytes += len(raw)
            if record["url"] in urls and urls[record["url"]] != record["sha256"]:
                raise ValueError("conflicting immutable URL snapshots")
            urls[record["url"]] = record["sha256"]
        except (OSError, ValueError, KeyError, EOFError) as exc:
            error = str(exc)
        if error:
            failures.append({"path": relative, "error": error})
    filings = read_jsonl(root / "data/manifests/filings.jsonl")
    return {
        "status": "passed" if records and not failures else "failed",
        "source_files": len(records),
        "unique_urls": len(urls),
        "original_bytes": total_bytes,
        "filing_count": len(filings),
        "failures": failures,
        "claim": "Archived bytes match the saved download hashes; this does not prove accounting truth.",
    }


def verify_fact_provenance(root: str | Path, facts: list) -> dict:
    root = Path(root)
    sources = {r["url"]: r for r in read_jsonl(root / "data/manifests/sources.jsonl")}
    failures = []
    counts = Counter()
    raw_cache: dict[str, bytes] = {}
    for fact in facts:
        counts[fact.status] += 1
        source = sources.get(fact.source_url)
        errors = []
        if source is None:
            errors.append("source_url_absent_from_manifest")
        elif source["sha256"] != fact.source_sha256:
            errors.append("fact_source_hash_mismatch")
        else:
            if fact.source_url not in raw_cache:
                raw_cache[fact.source_url] = gzip.decompress((root / source["local_path"]).read_bytes())
            raw = raw_cache[fact.source_url]
            if fact.evidence_anchor.startswith("#"):
                if fact.evidence_anchor[1:].encode() not in raw:
                    errors.append("fact_anchor_not_present_in_original_bytes")
            elif fact.context_id.encode() not in raw:
                errors.append("fallback_context_locator_not_present_in_original_bytes")
        if not fact.context_id or not fact.concept or not fact.evidence_anchor:
            errors.append("incomplete_fact_locator")
        if fact.status == "accepted" and not fact.concept_namespace:
            errors.append("accepted_real_fact_missing_namespace_uri")
        if errors:
            failures.append({"identity": fact.identity, "errors": errors})
    return {
        "status": "passed" if facts and not failures else "failed",
        "fact_count": len(facts),
        "status_counts": dict(counts),
        "failures": failures,
    }


def verify_support_files(root: str | Path) -> dict:
    """Verify vendored parsing code, source notices and offline taxonomy bytes."""
    root = Path(root).resolve()
    records = read_jsonl(root / "data/manifests/taxonomy_sources.jsonl")
    notices = root / "data/manifests/taxonomy_notices.json"
    vendor = root / "data/manifests/sec_transform_vendor.json"
    plain = json.loads(notices.read_text(encoding="utf-8")) if notices.exists() else []
    if vendor.exists():
        package = json.loads(vendor.read_text(encoding="utf-8"))
        plain.extend(package["files"])
        if package.get("supplemental_license_notice"):
            plain.append(package["supplemental_license_notice"])
    failures = []
    for record in records + plain:
        path = (root / record.get("local_path", record.get("path", ""))).resolve()
        try:
            if not path.is_relative_to(root):
                raise ValueError("support file escapes corpus root")
            data = path.read_bytes()
            if "compressed_sha256" in record:
                if hashlib.sha256(data).hexdigest() != record["compressed_sha256"]:
                    raise ValueError("compressed support hash mismatch")
                data = gzip.decompress(data)
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("support file hash mismatch")
        except (OSError, ValueError, KeyError, EOFError) as error:
            failures.append({"path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                             "error": str(error)})
    return {"status": "passed" if records and plain and not failures else "failed",
            "taxonomy_files": len(records), "vendor_and_notice_files": len(plain), "failures": failures}


def coverage_report(root: str | Path) -> dict:
    """Use the preregistered 72 company-years as the denominator, even if parsing fails."""
    root = Path(root)
    with (root / "data/universe.csv").open(encoding="utf-8", newline="") as handle:
        companies = list(csv.DictReader(handle))
    filings = read_jsonl(root / "data/manifests/filings.jsonl")
    parsed = [json.loads(path.read_text(encoding="utf-8")) for path in
              sorted((root / "data/manifests/parsed").glob("*.json"))]
    output = {}
    for split in ("development", "holdout"):
        members = [row for row in companies if row["split"] == split]
        targets_path = root / f"data/processed/{split}_targets.json"
        targets = json.loads(targets_path.read_text(encoding="utf-8")) if targets_path.exists() else []
        actual = {(str(row["cik"]).zfill(10), int(row["fiscal_year"])) for row in targets}
        missing = [{"cik": row["cik"], "ticker": row["ticker"], "fiscal_year": year}
                   for row in members for year in range(2019, 2025)
                   if (row["cik"].zfill(10), year) not in actual]
        collected = [row for row in filings if row["split"] == split]
        audits = [row for row in parsed if row["split"] == split]
        done = {row["accession"] for row in audits}
        output[split] = {
            "planned_companies": len(members), "planned_company_years": len(members) * 6,
            "identified_target_company_years": len(actual), "missing_company_years": missing,
            "collected_filings": len(collected), "parsed_filings": len(audits),
            "unparsed_accessions": [row["accession"] for row in collected if row["accession"] not in done],
            "parse_status_counts": dict(Counter(row["status"] for row in audits)),
            "filings_with_validation_messages": sum(bool(row.get("arelle_errors")) for row in audits),
            "note": "Target identification is separate from accepted-revenue or growth-query coverage.",
        }
    return output
