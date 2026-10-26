"""Independent checks of the disclosed annotation boundary, not revenue labels."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from filingtime import recovery


def put(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8", newline="\n")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    root.mkdir()
    freeze = put(root, "data/manifests/rule_freeze.json", {"source_manifest_hashes": {}})
    put(root, recovery.FIRST_FAILURE, {
        "status": "failed_closed", "freeze_record_sha256": sha(freeze),
        "outputs_existed_before": {"sample": False}, "outputs_exist_after": {"sample": False},
    })
    audit_path = "data/manifests/parsed/test-accession.json"
    audit = put(root, audit_path, {"accession": "test-accession", "split": "holdout",
                                  "fiscal_year_focus": "2020"})
    (root / "data/manifests/candidates").mkdir()
    raw = b'<html><body><div id="fiscal-period">Fiscal year 2019 ended February 1, 2020.</div></body></html>'
    archive = root / "data/raw/original.html.gz"
    archive.parent.mkdir()
    archive.write_bytes(gzip.compress(raw, mtime=0))
    source = {"url": "https://example.test/original.html", "local_path": "data/raw/original.html.gz",
              "sha256": hashlib.sha256(raw).hexdigest()}
    put(root, "data/manifests/sources.jsonl", source)
    registry = {
        "schema_version": 1, "created_after_first_evaluation": True,
        "untouched_holdout_claim": False, "human_review_status": "pending",
        "corrections": [{"accession": "test-accession", "field": "fiscal_year_focus",
            "original_value": "2020", "corrected_value": "2019",
            "audit_path": audit_path, "audit_sha256": sha(audit),
            "evidence": [{"source_url": source["url"], "archive_path": source["local_path"],
                          "sha256": source["sha256"], "anchor": "#fiscal-period",
                          "expected_text": "Fiscal year 2019 ended February 1, 2020."}]}],
    }
    put(root, recovery.CORRECTIONS, registry)
    put(root, "src/filingtime/recovery.py", {"fixture": True})
    monkeypatch.setattr(recovery, "check_freeze", lambda _: {"status": "unchanged"})
    monkeypatch.setattr(recovery, "RULE_PATHS", ())

    def normalize(stage, split):
        derived = json.loads((stage / audit_path).read_text(encoding="utf-8"))
        assert derived["fiscal_year_focus"] == "2019"
        assert split == "holdout"
        for relative in recovery.PRODUCTS:
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'{"year":2019}\r\n')
        return {"targets": 1, "split": "holdout"}

    monkeypatch.setattr(recovery, "normalize_corpus", normalize)
    return root, registry, audit


def test_recovery_changes_only_derived_copy_and_has_explicit_status(evidence, tmp_path):
    root, _, audit = evidence
    original = audit.read_bytes()
    result = recovery.recover_holdout(root, tmp_path / "work", publish=False)
    receipt = result["receipt"]
    assert receipt["untouched_holdout_claim"] is False
    assert receipt["original_frozen_evaluation_status"] == "failed_closed"
    assert receipt["evaluation_status"] == "post_evaluation_metadata_repaired_replay"
    assert audit.read_bytes() == original
    assert not (root / recovery.PRODUCTS[0]).exists()
    assert (Path(result["staging_root"]) / recovery.PRODUCTS[0]).read_bytes() == b'{"year":2019}\n'


def test_recovery_never_overwrites_existing_results(evidence, tmp_path):
    root, _, audit = evidence
    original = audit.read_bytes()
    recovery.recover_holdout(root, tmp_path / "work", publish=True)
    recovery.recover_holdout(root, tmp_path / "work", publish=True)  # identical is idempotent
    existing = root / recovery.PRODUCTS[0]
    existing.write_bytes(b'preserve this existing result\n')
    with pytest.raises(FileExistsError, match="Preserve existing"):
        recovery.recover_holdout(root, tmp_path / "work", publish=True)
    assert existing.read_bytes() == b'preserve this existing result\n'
    assert audit.read_bytes() == original


@pytest.mark.parametrize("tamper", ["audit", "source", "anchor", "excerpt", "untouched", "path"])
def test_recovery_rejects_unproven_correction(evidence, tmp_path, tamper):
    root, registry, audit = evidence
    correction = registry["corrections"][0]
    reference = correction["evidence"][0]
    if tamper == "audit":
        audit.write_text('{"fiscal_year_focus":"2021"}', encoding="utf-8")
    elif tamper == "source":
        (root / reference["archive_path"]).write_bytes(gzip.compress(b"different source"))
    elif tamper == "anchor":
        reference["anchor"] = "#nonexistent"
    elif tamper == "excerpt":
        reference["expected_text"] = "Fiscal year 2022 ended February 1, 2020."
    elif tamper == "untouched":
        registry["untouched_holdout_claim"] = True
    else:
        correction["audit_path"] = "../outside.json"
    put(root, recovery.CORRECTIONS, registry)
    with pytest.raises(ValueError):
        recovery.recover_holdout(root, tmp_path / "work", publish=True)
    assert not (root / recovery.PRODUCTS[0]).exists()
