"""Report checks use artificial summaries; no live held-out values are read."""

import hashlib
import json

import pytest

from filingtime import report


def _metric(ok, missing, ambiguous, rejected, future=0):
    return dict(total_queries=10, usable_count=ok, coverage=ok / 10,
                status_counts=dict(ok=ok, missing=missing, ambiguous=ambiguous, rejected=rejected),
                future_provenance_count=future, future_provenance_denominator=ok,
                future_provenance_rate=future / ok)


def _pair(both, baseline_only, pit_only, neither, changed=0):
    return dict(total_query_keys=10, both_usable_count=both,
                baseline_only_usable_count=baseline_only, pit_only_usable_count=pit_only,
                neither_usable_count=neither, numeric_changed_count=changed,
                numeric_changed_denominator=both, direction_changed_count=changed,
                direction_changed_denominator=both)


def _prepare(root, monkeypatch):
    monkeypatch.setattr(report, "check_freeze", lambda root: {"status": "unchanged"})
    monkeypatch.setattr(report, "coverage_report", lambda root: {})
    monkeypatch.setattr(report, "verify_corpus", lambda root: {"source_files": 0, "filing_count": 0, "status": "synthetic"})
    monkeypatch.setattr(report, "verify_support_files", lambda root: {"taxonomy_files": 0})
    monkeypatch.setattr(report, "version_changes", lambda root: [])
    monkeypatch.setattr(report, "_figure", lambda summaries, destination: None)
    results = root / "data/results"
    results.mkdir(parents=True)
    (root / "data/processed").mkdir()
    (root / "docs").mkdir()
    for split in ("development", "holdout"):
        relative = f"data/processed/{split}_facts.jsonl"
        (root / relative).write_text("", encoding="utf-8")
        digest = hashlib.sha256(b"").hexdigest()
        summary = {
            "input_files": [{"path": relative, "sha256": digest}], "output_files": [],
            "modes": {
                "period_end": {"revenue": _metric(6, 1, 2, 1, 2), "growth": _metric(4, 1, 1, 4, 2)},
                "latest": {"revenue": _metric(4, 2, 3, 1, 3), "growth": _metric(2, 2, 2, 4, 1)},
                "pit": {"revenue": _metric(4, 3, 2, 1), "growth": _metric(2, 3, 1, 4)},
            },
            "comparisons_to_pit": {
                "period_end": {"revenue": _pair(4, 2, 0, 4), "growth": _pair(2, 2, 0, 6)},
                "latest": {"revenue": _pair(2, 2, 2, 4, 1), "growth": _pair(1, 1, 1, 7, 1)},
            },
            "rankings": {"period_end": {"changed_memberships": 0, "common_memberships": 2},
                         "latest": {"changed_memberships": 1, "common_memberships": 2}},
        }
        (results / f"{split}_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        crosscheck = {"summary": {"input_facts_sha256": digest, "unique_accepted_facts": 4,
                                  "exact_match_count": 2, "comparable_count": 3,
                                  "status_counts": {"exact_match": 2, "numeric_mismatch": 1,
                                                    "no_exact_accession_period_match": 1}}}
        (results / f"{split}_companyfacts_crosscheck.json").write_text(json.dumps(crosscheck), encoding="utf-8")
    injections = {"temporal_summary": {"confusion_matrix": {"TP": 3, "FP": 0, "TN": 6, "FN": 0},
                                       "scoring_coverage": {"numerator": 9}, "observed_refusal_count": 3},
                  "semantic_summary": {"expectation_match_count": 8, "scenario_count": 8}}
    (results / "synthetic_injection_benchmark.json").write_text(json.dumps(injections), encoding="utf-8")
    input_content = {
        "data/manifests/holdout_first_evaluation.json": '{"status":"failed_closed"}',
        "data/reference/metadata_corrections.json": '{"synthetic_fixture_only":true}',
        "src/filingtime/recovery.py": "# synthetic recovery code identity\n",
    }
    for relative, content in input_content.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    output_paths = [f"data/processed/holdout_{suffix}" for suffix in ("facts.jsonl", "normalization.json", "targets.json")]
    for relative in output_paths[1:]:
        (root / relative).write_text("[]\n", encoding="utf-8")
    receipt = {
        "status": "passed", "evaluation_status": "post_evaluation_metadata_repaired_replay",
        "original_frozen_evaluation_status": "failed_closed", "untouched_holdout_claim": False,
        "inspection_after_first_holdout_failure": True, "corrections": [{"synthetic": True}],
        "input_files": [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in input_content],
        "output_files": [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in output_paths],
    }
    (root / "data/manifests/holdout_recovery.json").write_text(json.dumps(receipt), encoding="utf-8")


def test_report_preserves_full_refusal_and_paired_denominators(tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    report.build_report(tmp_path)
    text = (tmp_path / "docs/REPORT.md").read_text(encoding="utf-8")
    assert "| Development | Point in time | growth | 3 / 10 | 5 / 10 | 1; 4 |" in text
    assert "| Development | Latest-value baseline | revenue | 2 / 10 | 4 / 10 | 3; 1 |" in text
    assert "| Development | Period-end baseline | revenue | 4 | 2 | 0 | 4 | 10 |" in text
    assert "| Development | Latest-value baseline | growth | 1 | 1 | 1 | 7 | 10 |" in text
    assert "| Development | 4 | 2 | 1 | 1 |" in text
    assert "| Former holdout (repaired) | Point in time | growth | 3 / 10 | 5 / 10 | 1; 4 |" in text
    assert "first frozen evaluation failed closed" in text
    assert "not untouched holdout results" in text
    assert "independent human review remains pending" in text
    assert "3 refusals are separate" in text
    assert "not real-world precision/recall estimates" in text


def test_report_rejects_a_stale_experiment_instead_of_combining_snapshots(tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    (tmp_path / "data/processed/development_facts.jsonl").write_text("changed input", encoding="utf-8")
    with pytest.raises(ValueError, match="Stale experiment summary"):
        report.build_report(tmp_path)
    assert not (tmp_path / "docs/REPORT.md").exists()


@pytest.mark.parametrize("freeze_status", ["missing", "changed"])
def test_report_gate_precedes_all_heldout_reads(tmp_path, monkeypatch, freeze_status):
    monkeypatch.setattr(report, "check_freeze", lambda root: {"status": freeze_status})
    with pytest.raises(ValueError, match="unchanged frozen"):
        report.build_report(tmp_path)
    with pytest.raises(ValueError, match="unchanged frozen"):
        report.version_changes(tmp_path)
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("relative", [
    "data/manifests/holdout_first_evaluation.json", "data/reference/metadata_corrections.json",
    "src/filingtime/recovery.py", "data/processed/holdout_facts.jsonl",
    "data/processed/holdout_normalization.json", "data/processed/holdout_targets.json",
])
def test_report_rejects_stale_recovery_inputs_and_products(tmp_path, monkeypatch, relative):
    _prepare(tmp_path, monkeypatch)
    (tmp_path / relative).write_text("changed evidence", encoding="utf-8")
    with pytest.raises(ValueError, match="Stale recovery receipt"):
        report.build_report(tmp_path)
    assert not (tmp_path / "docs/REPORT.md").exists()


@pytest.mark.parametrize("field,value", [
    ("untouched_holdout_claim", True),
    ("original_frozen_evaluation_status", "passed"),
    ("inspection_after_first_holdout_failure", False),
])
def test_report_cannot_upgrade_repair_to_untouched_success(tmp_path, monkeypatch, field, value):
    _prepare(tmp_path, monkeypatch)
    path = tmp_path / "data/manifests/holdout_recovery.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt[field] = value
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="disclose the failed original evaluation"):
        report.build_report(tmp_path)
