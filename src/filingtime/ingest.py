"""Immutable SEC source collection. No financial values are inferred here."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

UTC = timezone.utc
FORMS = {"10-K", "10-K/A"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def available_at(accepted_at: str) -> str:
    """The preregistered 24-hour lag is a convention, not an observed feed latency."""
    dt = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("SEC acceptance timestamp must carry an explicit timezone")
    return (dt.astimezone(UTC) + timedelta(hours=24)).isoformat().replace("+00:00", "Z")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_source(root: Path, record: dict[str, Any], verify: bool = True) -> bytes:
    file = (root / record["local_path"]).resolve()
    if not file.is_relative_to(root.resolve()):
        raise ValueError("Source path escapes the corpus root")
    compressed = file.read_bytes()
    if verify and sha256(compressed) != record["compressed_sha256"]:
        raise ValueError(f"Compressed source hash mismatch: {record['local_path']}")
    data = gzip.decompress(compressed)
    if verify and sha256(data) != record["sha256"]:
        raise ValueError(f"Original source hash mismatch: {record['local_path']}")
    return data


class SecCollector:
    """Serial, rate-limited downloader with source-level resumability.

    The contact-bearing User-Agent is provided at runtime, never stored in the
    public source manifest. Existing snapshots are verified and reused.
    """

    def __init__(self, root: Path, user_agent: str | None = None, interval: float = 0.5):
        self.root = root.resolve()
        self.user_agent = user_agent or os.environ.get("SEC_USER_AGENT", "")
        if not self.user_agent or "@" not in self.user_agent:
            raise ValueError("Set SEC_USER_AGENT to an application name and real contact email")
        self.interval = max(0.5, interval)
        self._last_request = 0.0
        self.sources_path = self.root / "data/manifests/sources.jsonl"
        self.sources = {r["url"]: r for r in load_jsonl(self.sources_path)}
        self.selection_audit: dict[str, dict[str, Any]] = {}

    def fetch(self, url: str, local_path: str, role: str) -> tuple[bytes, dict[str, Any]]:
        """Save raw response bytes, without reserializing JSON or changing HTML."""
        if url in self.sources:
            record = self.sources[url]
            return read_source(self.root, record), record
        if urlsplit(url).scheme != "https":
            raise ValueError("Only HTTPS source URLs are supported")
        target = (self.root / local_path).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Output path escapes corpus root")
        if target.exists():
            raise FileExistsError(f"Unmanifested existing file: {target}")
        last_error: Exception | None = None
        for attempt in range(5):
            time.sleep(max(0, self.interval - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            request = Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
            try:
                with urlopen(request, timeout=90) as response:
                    data = response.read()
                    content_type = response.headers.get("Content-Type", "")
                break
            except HTTPError as error:
                last_error = error
                if error.code not in {403, 429, 500, 502, 503, 504}:
                    raise
                time.sleep(min(30, 2 ** (attempt + 1)))
            except (URLError, TimeoutError, ConnectionError, HTTPException) as error:
                last_error = error
                time.sleep(min(30, 2 ** (attempt + 1)))
        else:
            raise RuntimeError(f"SEC download failed after retries: {url}") from last_error
        compressed = gzip.compress(data, compresslevel=9, mtime=0)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(compressed)
        record = {
            "url": url, "local_path": target.relative_to(self.root).as_posix(),
            "role": role, "retrieved_at": utc_now(), "sha256": sha256(data),
            "compressed_sha256": sha256(compressed), "bytes": len(data),
            "compressed_bytes": len(compressed), "content_type": content_type,
        }
        append_jsonl(self.sources_path, record)
        self.sources[url] = record
        return data, record

    def company_filings(self, cik: str, start: str = "2019-01-01", end: str = "2025-12-31") -> tuple[dict[str, Any], list[dict[str, Any]]]:
        cik = str(cik).zfill(10)
        data, _ = self.fetch(f"https://data.sec.gov/submissions/CIK{cik}.json", f"data/raw/{cik}/metadata/submissions.json.gz", "submissions_metadata")
        metadata = json.loads(data)
        pages = [metadata["filings"]["recent"]]
        for page in metadata["filings"].get("files", []):
            if page["filingTo"] < start or page["filingFrom"] > end:
                continue
            data, _ = self.fetch("https://data.sec.gov/submissions/" + page["name"], f"data/raw/{cik}/metadata/{page['name']}.gz", "historical_submissions_metadata")
            pages.append(json.loads(data))
        records: dict[str, dict[str, Any]] = {}
        for page in pages:
            for index, form in enumerate(page.get("form", [])):
                date = page["filingDate"][index]
                if form not in FORMS or not start <= date <= end:
                    continue
                record = {key: values[index] for key, values in page.items() if isinstance(values, list) and index < len(values)}
                record["cik"] = cik
                records[record["accessionNumber"]] = record
        cutoff = datetime.fromisoformat(end + "T23:59:59+00:00")
        selected, excluded = [], []
        for record in records.values():
            accepted = datetime.fromisoformat(record["acceptanceDateTime"].replace("Z", "+00:00"))
            if accepted.tzinfo is None:
                raise ValueError(f"Naive SEC acceptance timestamp: {record['accessionNumber']}")
            if accepted.astimezone(UTC) <= cutoff:
                selected.append(record)
            else:
                excluded.append(record["accessionNumber"])
        self.selection_audit[cik] = {
            "cik": cik, "filing_date_start": start, "filing_date_end": end,
            "accepted_cutoff_utc": cutoff.isoformat().replace("+00:00", "Z"),
            "forms_and_filing_date_candidates": len(records),
            "accepted_cutoff_excluded_count": len(excluded),
            "accepted_cutoff_excluded_accessions": sorted(excluded),
            "selected_count": len(selected),
        }
        return metadata, sorted(selected, key=lambda r: (r["filingDate"], r["accessionNumber"]))

    def collect_filing(self, company: dict[str, str], filing: dict[str, Any]) -> dict[str, Any]:
        cik = company["cik"].zfill(10)
        accession = filing["accessionNumber"]
        base_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        local = f"data/raw/{cik}/{accession}"
        index_data, _ = self.fetch(base_url + "index.json", f"{local}/index.json.gz", "filing_directory_index")
        items = json.loads(index_data)["directory"]["item"]
        primary = filing["primaryDocument"]
        selected = {primary: "primary_filing"}
        for item in items:
            name = item["name"]
            lower = name.lower()
            if lower.endswith(".xsd"):
                selected[name] = "issuer_taxonomy_schema"
            elif lower.endswith(".xml") and not re.fullmatch(r"r\d+\.xml", lower):
                selected[name] = "filing_summary" if lower == "filingsummary.xml" else "xbrl_dependency_or_instance"
        files = []
        for name, role in sorted(selected.items()):
            _, source = self.fetch(base_url + name, f"{local}/{name}.gz", role)
            files.append(source)
        primary_source = next(r for r in files if r["role"] == "primary_filing")
        accepted = filing.get("acceptanceDateTime", "")
        if not accepted:
            raise ValueError(f"Missing acceptanceDateTime for {accession}")
        return {
            "cik": cik, "ticker": company["ticker"], "split": company["split"],
            "accession": accession, "form": filing["form"], "filing_date": filing["filingDate"],
            "report_date": filing.get("reportDate", ""), "accepted_at": accepted,
            "available_at": available_at(accepted), "primary_document": primary,
            "source_url": primary_source["url"], "source_sha256": primary_source["sha256"],
            "retrieved_at": primary_source["retrieved_at"], "primary_path": primary_source["local_path"],
            "is_inline_xbrl": bool(filing.get("isInlineXBRL", 0)),
            "is_xbrl": bool(filing.get("isXBRL", 0)),
            "files": [{"url": r["url"], "local_path": r["local_path"], "sha256": r["sha256"], "role": r["role"]} for r in files],
        }


def read_universe(root: Path) -> list[dict[str, str]]:
    with (root / "data/universe.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))
