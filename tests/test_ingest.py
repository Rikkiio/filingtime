"""Source integrity and time tests independent of network availability."""

import gzip
import json
from http.client import RemoteDisconnected
from pathlib import Path

import pytest

from filingtime.ingest import SecCollector, available_at, read_source, sha256


def test_availability_is_24_hours_after_aware_acceptance():
    assert available_at("2019-10-30T22:12:36.000Z") == "2019-10-31T22:12:36Z"
    assert available_at("2024-12-31T23:30:00-05:00") == "2025-01-02T04:30:00Z"
    with pytest.raises(ValueError, match="timezone"):
        available_at("2024-12-31T23:30:00")


def test_source_verifier_detects_raw_and_compressed_tampering(tmp_path: Path):
    original = b"<xbrl>original source bytes</xbrl>"
    compressed = gzip.compress(original, mtime=0)
    file = tmp_path / "source.gz"
    file.write_bytes(compressed)
    record = {"local_path": "source.gz", "sha256": sha256(original), "compressed_sha256": sha256(compressed)}
    assert read_source(tmp_path, record) == original
    record["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Original source hash"):
        read_source(tmp_path, record)
    file.write_bytes(gzip.compress(b"changed", mtime=0))
    with pytest.raises(ValueError, match="Compressed source hash"):
        read_source(tmp_path, record)


def test_source_path_cannot_escape_corpus(tmp_path: Path):
    with pytest.raises(ValueError, match="escapes"):
        read_source(tmp_path, {"local_path": "../outside.gz"})


def test_cached_source_is_verified_and_reused_without_network(tmp_path: Path, monkeypatch):
    original = b'{"source":"frozen"}'
    compressed = gzip.compress(original, mtime=0)
    (tmp_path / "source.gz").write_bytes(compressed)
    record = {"url": "https://example.com/source", "local_path": "source.gz", "sha256": sha256(original), "compressed_sha256": sha256(compressed)}
    manifests = tmp_path / "data/manifests"
    manifests.mkdir(parents=True)
    (manifests / "sources.jsonl").write_text(json.dumps(record) + "\n")
    def forbidden(*args, **kwargs):
        pytest.fail("Frozen snapshot attempted a network request")
    monkeypatch.setattr("filingtime.ingest.urlopen", forbidden)
    collector = SecCollector(tmp_path, user_agent="Test collector contact nobody@example.com")
    actual, source = collector.fetch(record["url"], "unused.gz", "primary_filing")
    assert actual == original
    assert source == record


def test_filing_date_does_not_override_utc_acceptance_cutoff(tmp_path: Path, monkeypatch):
    metadata = {"filings": {"files": [], "recent": {
        "form": ["10-K", "10-K", "10-Q"],
        "filingDate": ["2025-12-31", "2025-12-31", "2025-12-30"],
        "accessionNumber": ["early", "late", "quarter"],
        "acceptanceDateTime": ["2025-12-31T23:00:00Z", "2026-01-01T01:00:00Z", "2025-12-30T12:00:00Z"],
    }}}
    collector = SecCollector(tmp_path, user_agent="Test collector contact nobody@example.com")
    monkeypatch.setattr(collector, "fetch", lambda *args: (json.dumps(metadata).encode(), {}))
    _, selected = collector.company_filings("320193")
    assert [row["accessionNumber"] for row in selected] == ["early"]
    assert collector.selection_audit["0000320193"]["accepted_cutoff_excluded_accessions"] == ["late"]


def test_transient_disconnect_retries_without_partial_snapshot(tmp_path: Path, monkeypatch):
    calls = []
    class Response:
        headers = {"Content-Type": "application/xml"}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b"<xbrl>complete</xbrl>"
    def request(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RemoteDisconnected("transient server close")
        return Response()
    monkeypatch.setattr("filingtime.ingest.urlopen", request)
    monkeypatch.setattr("filingtime.ingest.time.sleep", lambda _: None)
    collector = SecCollector(tmp_path, user_agent="Test collector contact nobody@example.com")
    data, record = collector.fetch("https://example.com/source", "source.gz", "primary_filing")
    assert len(calls) == 2
    assert read_source(tmp_path, record) == data == b"<xbrl>complete</xbrl>"
    assert len((tmp_path / "data/manifests/sources.jsonl").read_text().splitlines()) == 1
