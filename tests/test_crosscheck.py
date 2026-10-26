"""Independent synthetic checks for false API agreement; never live held-out data."""

from dataclasses import replace
import gzip
import hashlib
import json

import pytest

from filingtime.crosscheck import crosscheck_companyfacts
from filingtime.models import RevenueFact, save_facts


def _fact(**changes):
    values = dict(
        cik="9999999998", accession="synthetic-original", form="10-K",
        period_start="2023-01-01", period_end="2023-12-31", value="120", unit="USD",
        concept="us-gaap:Revenues", concept_namespace="http://fasb.org/us-gaap/2024",
        context_id="synthetic-annual", accepted_at="2024-02-01T12:00:00Z",
        source_url="https://example.invalid/synthetic-crosscheck.html", source_sha256="e" * 64,
        fact_id="synthetic-revenue", basis_id="synthetic-total", status="accepted",
    )
    return RevenueFact(**(values | changes))


def _api_record(**changes):
    return dict(accn="synthetic-original", start="2023-01-01", end="2023-12-31", val=120) | changes


def _setup(root, facts=None, *, records=None, unit="USD", payload_cik=9999999998, split="development"):
    payload = {"cik": payload_cik, "facts": {"us-gaap": {"Revenues": {
        "units": {unit: records if records is not None else [_api_record()]}}}}}
    raw = json.dumps(payload).encode()
    compressed = gzip.compress(raw, mtime=0)
    relative = "data/raw/synthetic-companyfacts.json.gz"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(compressed)
    source = dict(url="https://data.sec.gov/api/xbrl/companyfacts/CIK9999999998.json",
                  local_path=relative, sha256=hashlib.sha256(raw).hexdigest(),
                  compressed_sha256=hashlib.sha256(compressed).hexdigest())
    manifest = root / "data/manifests/sources.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(source) + "\n", encoding="utf-8")
    save_facts(root / f"data/processed/{split}_facts.jsonl", facts if facts is not None else [_fact()])


def _rows(root, split="development"):
    return json.loads((root / f"data/results/{split}_companyfacts_crosscheck.json").read_text())["observations"]


def test_identical_accession_period_currency_value_has_extraction_agreement(tmp_path):
    _setup(tmp_path)
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["status_counts"] == {"exact_match": 1}
    assert summary["comparable_count"] == 1
    assert summary["extraction_agreement"] == 1
    assert summary["human_review_status"] == "pending"


@pytest.mark.parametrize("change", [
    {"accn": "synthetic-next-filing"}, {"start": "2023-04-01"}, {"end": "2023-12-30"},
    {"start": None}, {"accn": None},
])
def test_matching_amount_does_not_override_exact_source_and_period_keys(tmp_path, change):
    _setup(tmp_path, records=[_api_record(**change)])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["exact_match_count"] == 0
    assert summary["comparable_count"] == 0
    assert summary["extraction_agreement"] is None
    assert _rows(tmp_path)[0]["status"] == "no_exact_accession_period_match"


def test_identical_amount_in_another_currency_cannot_match(tmp_path):
    _setup(tmp_path, unit="EUR")
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["exact_match_count"] == 0
    assert summary["comparable_count"] == 0


def test_conflicting_api_duplicates_are_not_a_match_even_if_one_value_matches(tmp_path):
    _setup(tmp_path, records=[_api_record(), _api_record(val=999)])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["status_counts"] == {"api_conflicting_values": 1}
    assert summary["comparable_count"] == 0
    assert summary["extraction_agreement"] is None
    assert _rows(tmp_path)[0]["sec_extracted_values"] == ["120", "999"]


def test_repeated_equivalent_api_observations_do_not_create_a_conflict(tmp_path):
    _setup(tmp_path, records=[_api_record(), _api_record(val=120.0)])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["status_counts"] == {"exact_match": 1}


def test_extension_local_name_cannot_borrow_the_standard_concept_value(tmp_path):
    _setup(tmp_path, [_fact(concept="issuer:Revenues", concept_namespace="https://example.invalid/issuer/2024")])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["status_counts"] == {"extension_not_covered_by_api": 1}
    assert summary["exact_match_count"] == 0


def test_actual_standard_namespace_is_valid_even_with_an_alternative_xml_prefix(tmp_path):
    _setup(tmp_path, [_fact(concept="gaap_alias:Revenues")])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["exact_match_count"] == 1


def test_dimensional_amount_cannot_borrow_an_undimensioned_api_match(tmp_path):
    _setup(tmp_path, [_fact(dimensions='{"BusinessSegmentAxis":"WidgetMember"}')])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["exact_match_count"] == 0
    assert summary["status_counts"] == {"dimensional_fact_not_covered_by_api": 1}


@pytest.mark.parametrize("namespace", [
    "https://example.invalid/issuer/2024", "http://fasb.org.evil.invalid/us-gaap/2024",
    "http://fasb.org/us-gaap/2024/custom",
])
def test_forged_us_gaap_prefix_cannot_create_exact_api_agreement(tmp_path, namespace):
    _setup(tmp_path, [_fact(concept_namespace=namespace)])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["exact_match_count"] == 0
    assert summary["unique_accepted_facts"] == 1


def test_deduplication_cannot_hide_a_different_actual_concept_namespace(tmp_path):
    real = _fact()
    fake = replace(real, fact_id="synthetic-forged", concept_namespace="https://example.invalid/custom")
    _setup(tmp_path, [real, fake])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["unique_accepted_facts"] == 2
    assert summary["exact_match_count"] == 1


def test_equivalent_source_duplicates_have_an_explicit_before_dedup_count(tmp_path):
    original = _fact()
    _setup(tmp_path, [original, replace(original, fact_id="same-value-second-node")])
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["source_fact_count_before_deduplication"] == 2
    assert summary["unique_accepted_facts"] == 1


def test_a_snapshot_for_another_entity_cannot_create_agreement(tmp_path):
    _setup(tmp_path, payload_cik=12345)
    try:
        summary = crosscheck_companyfacts(tmp_path, "development")
    except ValueError:
        return  # Rejecting the entire invalid snapshot is also conservative.
    assert summary["exact_match_count"] == 0
    assert summary["comparable_count"] == 0


def test_zero_comparable_and_missing_snapshot_remain_visible(tmp_path):
    _setup(tmp_path)
    (tmp_path / "data/manifests/sources.jsonl").write_text("", encoding="utf-8")
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["unique_accepted_facts"] == 1
    assert summary["status_counts"] == {"no_companyfacts_snapshot": 1}
    assert summary["extraction_agreement"] is None


def test_agreement_denominator_does_not_silently_count_unresolved_cases_as_matches(tmp_path):
    facts = [_fact(accession=name, fact_id=name) for name in ("match", "mismatch", "missing", "conflict")]
    facts.append(_fact(accession="extension", fact_id="extension", concept="issuer:Revenues",
                       concept_namespace="https://example.invalid/issuer/2024"))
    records = [_api_record(accn="match"), _api_record(accn="mismatch", val=121),
               _api_record(accn="conflict"), _api_record(accn="conflict", val=999)]
    _setup(tmp_path, facts, records=records)
    summary = crosscheck_companyfacts(tmp_path, "development")
    assert summary["unique_accepted_facts"] == 5
    assert summary["comparable_count"] == 2
    assert summary["exact_match_count"] == 1
    assert summary["extraction_agreement"] == 0.5
    assert sum(summary["status_counts"].values()) == 5


@pytest.mark.parametrize("freeze_status", ["missing", "changed"])
def test_holdout_gate_runs_before_loading_any_values(tmp_path, monkeypatch, freeze_status):
    import filingtime.crosscheck
    import filingtime.freeze

    monkeypatch.setattr(filingtime.freeze, "check_freeze", lambda root: {"status": freeze_status})
    def unexpected_read(*args, **kwargs):
        pytest.fail("Held-out values or source manifests were read before the freeze gate")
    monkeypatch.setattr(filingtime.crosscheck, "load_facts", unexpected_read)
    monkeypatch.setattr(filingtime.crosscheck, "load_jsonl", unexpected_read)
    with pytest.raises(ValueError, match="frozen"):
        crosscheck_companyfacts(tmp_path, "holdout")
    assert not (tmp_path / "data/results").exists()


def test_unchanged_gate_allows_only_the_requested_synthetic_split(tmp_path, monkeypatch):
    import filingtime.freeze

    _setup(tmp_path, split="holdout")
    monkeypatch.setattr(filingtime.freeze, "check_freeze", lambda root: {"status": "unchanged"})
    summary = crosscheck_companyfacts(tmp_path, "holdout", write=False)
    assert summary["exact_match_count"] == 1
    assert not (tmp_path / "data/results").exists()


def test_snapshot_hash_corruption_fails_instead_of_producing_agreement(tmp_path):
    _setup(tmp_path)
    path = tmp_path / "data/raw/synthetic-companyfacts.json.gz"
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="hash mismatch"):
        crosscheck_companyfacts(tmp_path, "development")
