"""The CLI is exercised with explicit synthetic fixtures and real subprocesses."""

import json
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import replace

import pytest

from filingtime.cli import main
from filingtime.models import RevenueFact, save_facts


def prepare(tmp_path):
    fact = RevenueFact(
        cik="1", accession="synthetic-cli", form="10-K", period_start="2023-01-01", period_end="2023-12-31",
        value="120", unit="USD", concept="us-gaap:Revenues", context_id="annual",
        accepted_at="2024-02-01T12:00:00Z", source_url="https://example.invalid/synthetic-cli",
        source_sha256="a" * 64, fact_id="synthetic-revenue", basis_id="synthetic-basis", status="accepted",
        evidence_anchor="#synthetic-revenue",
    )
    save_facts(tmp_path / "data/processed/development_facts.jsonl", [fact])
    return fact


def test_query_command_returns_json_with_source_evidence(tmp_path, capsys):
    fact = prepare(tmp_path)
    assert main(["query", "--root", str(tmp_path), "--cik", "1", "--period-end", "2023-12-31", "--as-of", "2024-03-01"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok" and result["value"] == "120"
    assert result["fact"]["source_sha256"] == fact.source_sha256
    assert result["fact"]["evidence_anchor"] == fact.evidence_anchor


def test_demo_displays_boundary_and_contaminated_baseline(tmp_path, capsys):
    prepare(tmp_path)
    assert main(["demo", "--root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["before"]["status"] == "missing"
    assert result["at_availability"]["status"] == "ok"
    assert result["biased_period_end"]["uses_future_information"]
    assert result["human_review_status"] == "pending"


def test_missing_corpus_returns_actionable_json_error(tmp_path, capsys):
    assert main(["demo", "--root", str(tmp_path)]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "No processed facts" in json.loads(output.err)["error"]


def test_unknown_timezone_is_rejected_instead_of_guessed(tmp_path, capsys):
    prepare(tmp_path)
    assert main(["query", "--root", str(tmp_path), "--cik", "1", "--period-end", "2023-12-31",
                 "--as-of", "2024-03-01T12:00:00"]) == 2
    assert "timezone" in json.loads(capsys.readouterr().err)["error"]


def test_growth_refusal_is_reported_as_data_status(tmp_path, capsys):
    prepare(tmp_path)
    assert main(["query", "--root", str(tmp_path), "--cik", "1", "--period-end", "2023-12-31",
                 "--as-of", "2024-03-01", "--growth"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "rejected"
    assert result["reason"] == "no_same_filing_adjacent_annual_predecessor"


def test_module_entrypoint_runs_outside_repository(tmp_path):
    prepare(tmp_path)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-m", "filingtime.cli", "demo", "--root", str(tmp_path)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["at_availability"]["value"] == "120"


def test_installed_console_entrypoint_exposes_version():
    executable = Path(sys.executable).parent / ("filingtime.exe" if os.name == "nt" else "filingtime")
    result = subprocess.run([str(executable), "--version"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert result.stdout.strip()


def test_verify_empty_corpus_exits_nonzero(tmp_path, capsys):
    assert main(["verify", "--root", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["corpus"]["status"] == "failed"


def test_build_store_and_query_use_exact_normalized_evidence(tmp_path, capsys):
    from filingtime.store import FactStore
    fact = prepare(tmp_path)
    assert main(["build-store", "--root", str(tmp_path), "--split", "development"]) == 0
    assert json.loads(capsys.readouterr().out)["fact_count"] == 1
    assert FactStore(tmp_path / "data/processed/stores/development").load() == [fact]
    assert main(["query", "--root", str(tmp_path), "--cik", "1", "--period-end", "2023-12-31", "--as-of", "2024-03-01"]) == 0
    assert json.loads(capsys.readouterr().out)["value"] == "120"


def test_query_rejects_stale_parquet_instead_of_using_changed_json(tmp_path, capsys):
    fact = prepare(tmp_path)
    assert main(["build-store", "--root", str(tmp_path), "--split", "development"]) == 0
    capsys.readouterr()
    save_facts(tmp_path / "data/processed/development_facts.jsonl", [replace(fact, value="999")])
    assert main(["query", "--root", str(tmp_path), "--cik", "1", "--period-end", "2023-12-31", "--as-of", "2024-03-01"]) == 2
    assert "Parquet store differs" in json.loads(capsys.readouterr().err)["error"]


def _reproduction_fixture(root):
    """Synthetic rule receipts exercise the replay tool, not holdout science."""
    from filingtime.experiment import run_experiment
    from filingtime.freeze import RULE_PATHS
    prepare(root)
    facts = (root / "data/processed/development_facts.jsonl").read_bytes()
    (root / "data/processed/holdout_facts.jsonl").write_bytes(facts)
    for split in ("development", "holdout"):
        target = {"cik": "1", "ticker": "SYNTHETIC", "fiscal_year": 2023,
                  "period_end": "2023-12-31", "split": split, "accession": "synthetic-cli"}
        (root / f"data/processed/{split}_targets.json").write_text(json.dumps([target]), encoding="utf-8")
    hashes = {}
    for relative in RULE_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic rule bytes\n", encoding="utf-8")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "src/filingtime/recovery.py").write_text("synthetic recovery source\n", encoding="utf-8")
    freeze = root / "data/manifests/rule_freeze.json"
    freeze.parent.mkdir(parents=True, exist_ok=True)
    source_hashes = {}
    for relative in ("data/manifests/sources.jsonl", "data/manifests/filings.jsonl"):
        source = root / relative
        source.write_text('{}\n', encoding="utf-8", newline="\n")
        source_hashes[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    freeze.write_text(json.dumps({"created_at": "synthetic-test-only", "rule_hashes": hashes,
                                  "source_manifest_hashes": source_hashes}), encoding="utf-8")
    for split in ("development", "holdout"):
        run_experiment(root, split)
    script = Path(__file__).resolve().parents[1] / "scripts/reproduce.py"
    spec = importlib.util.spec_from_file_location("filingtime_reproduction_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reproduction_replays_in_separate_directory(tmp_path):
    root = tmp_path / "reference"
    module = _reproduction_fixture(root)
    result = module.replay_experiments(root, tmp_path / "work")
    assert result["status"] == "passed" and result["artifact_count"] == 6
    for name in ("sources.jsonl", "filings.jsonl"):
        assert (tmp_path / "work/experiment-replay/data/manifests" / name).read_bytes() == (root / "data/manifests" / name).read_bytes()


def test_reproduction_mismatch_preserves_reference_files(tmp_path, monkeypatch):
    root = tmp_path / "reference"
    module = _reproduction_fixture(root)
    original = {path.name: path.read_bytes() for path in (root / "data/results").iterdir()}
    real_run = module.run_experiment
    def faulty_run(staging, split):
        result = real_run(staging, split)
        (staging / f"data/results/{split}_observations.csv").write_text("synthetic corruption", encoding="utf-8")
        return result
    monkeypatch.setattr(module, "run_experiment", faulty_run)
    with pytest.raises(ValueError, match="baselines were not overwritten"):
        module.replay_experiments(root, tmp_path / "work")
    assert original == {path.name: path.read_bytes() for path in (root / "data/results").iterdir()}


def test_reproduction_refuses_missing_frozen_source_manifest(tmp_path):
    root = tmp_path / "reference"
    module = _reproduction_fixture(root)
    (root / "data/manifests/sources.jsonl").unlink()
    with pytest.raises(FileNotFoundError):
        module.replay_experiments(root, tmp_path / "work")


def test_reproduction_refuses_changed_frozen_source_manifest(tmp_path):
    root = tmp_path / "reference"
    module = _reproduction_fixture(root)
    source = root / "data/manifests/filings.jsonl"
    source.write_text('{"synthetic_changed": true}\n', encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="unchanged frozen rules"):
        module.replay_experiments(root, tmp_path / "work")


def _write_synthetic_report(root, *, corrupt=False):
    from PIL import Image
    report = root / "docs/REPORT.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("synthetic corrupted report\n" if corrupt else "synthetic report\n", encoding="utf-8", newline="\n")
    results = root / "data/results"
    results.mkdir(parents=True, exist_ok=True)
    (results / "source_coverage.json").write_text('{}\n', encoding="utf-8", newline="\n")
    (results / "source_version_changes.csv").write_text("synthetic,column\n", encoding="utf-8", newline="\n")
    figures = root / "docs/assets"
    figures.mkdir(parents=True, exist_ok=True)
    picture = Image.new("RGB", (800, 450), "white")
    picture.putpixel((0, 0), (0, 0, 0))
    picture.save(figures / "research_summary.png")
    (figures / "research_summary.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450"><rect width="800" height="450" fill="white" /></svg>', encoding="utf-8")


def test_report_replay_checks_text_and_decodes_figures(tmp_path, monkeypatch):
    from filingtime import report
    root = tmp_path / "reference"
    module = _reproduction_fixture(root)
    _write_synthetic_report(root)
    monkeypatch.setattr(report, "build_report", _write_synthetic_report)
    result = module.replay_report(root, tmp_path / "work")
    assert result["status"] == "passed" and result["artifact_count"] == 3
    assert result["figures"]["png"]["width"] == 800
    assert result["figures"]["svg"]["view_box"] == [0.0, 0.0, 800.0, 450.0]


def test_report_replay_tampering_cannot_overwrite_baseline(tmp_path, monkeypatch):
    from filingtime import report
    root = tmp_path / "reference"
    module = _reproduction_fixture(root)
    _write_synthetic_report(root)
    before = (root / "docs/REPORT.md").read_bytes()
    monkeypatch.setattr(report, "build_report", lambda path: _write_synthetic_report(path, corrupt=True))
    with pytest.raises(ValueError, match="Report replay mismatch; baselines were not overwritten"):
        module.replay_report(root, tmp_path / "work")
    assert (root / "docs/REPORT.md").read_bytes() == before


def _recovery_replay_fixture(root, monkeypatch, *, failure_mode="expected", repair_mode="exact"):
    """Synthetic adapter faults; the real recovery module has its own source tests."""
    from filingtime import normalize, recovery
    module = _reproduction_fixture(root)
    products = tuple(f"data/processed/holdout_{suffix}" for suffix in
                     ("facts.jsonl", "normalization.json", "targets.json"))
    (root / products[1]).write_text('[]\n', encoding="utf-8", newline="\n")
    for relative in ("data/raw", "data/manifests/candidates", "data/manifests/parsed", "data/reference"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "data/raw/synthetic.xml").write_text("<synthetic/>", encoding="utf-8")
    audit = root / "data/manifests/parsed/synthetic.json"
    audit.write_text('{"synthetic":true}\n', encoding="utf-8", newline="\n")
    (root / "data/manifests/candidates/synthetic.jsonl").write_text('{}\n', encoding="utf-8", newline="\n")
    (root / "data/reference/metadata_corrections.json").write_text('{"synthetic":true}\n', encoding="utf-8", newline="\n")
    first = {
        "status": "failed_closed", "failure": {"exception": "ValueError", "message": "synthetic fiscal-year conflict"},
        "freeze_record_sha256": hashlib.sha256((root / "data/manifests/rule_freeze.json").read_bytes()).hexdigest(),
        "conflicting_original_audits": [{"path": audit.relative_to(root).as_posix(), "sha256": hashlib.sha256(audit.read_bytes()).hexdigest()}],
    }
    (root / "data/manifests/holdout_first_evaluation.json").write_text(json.dumps(first), encoding="utf-8")
    receipt = {
        "status": "passed", "evaluation_status": "post_evaluation_metadata_repaired_replay",
        "original_frozen_evaluation_status": "failed_closed", "untouched_holdout_claim": False,
        "inspection_after_first_holdout_failure": True, "human_review_status": "pending",
    }
    (root / "data/manifests/holdout_recovery.json").write_text(json.dumps(receipt), encoding="utf-8")

    def original_normalize(stage, split):
        assert stage != root and split == "holdout"
        if failure_mode == "unexpected_success":
            return {}
        if failure_mode == "wrong_exception":
            raise RuntimeError("synthetic fiscal-year conflict")
        if failure_mode == "changed_output":
            (stage / products[0]).write_text("synthetic overwritten output", encoding="utf-8")
        raise ValueError("synthetic fiscal-year conflict")

    def repaired(source_root, work_dir, *, publish=False):
        assert source_root == root and publish is False
        stage = work_dir / "synthetic-repaired"
        for relative in products:
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            # The real recovery canonicalizes only newly derived products.
            destination.write_text((root / relative).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        if repair_mode == "changed_output":
            (stage / products[0]).write_text("synthetic bad recovery", encoding="utf-8")
        labels = dict(receipt)
        if repair_mode == "false_untouched_claim":
            labels["untouched_holdout_claim"] = True
        return {"staging_root": str(stage), "receipt": labels}

    # Canonicalize the synthetic repaired baseline exactly as the real path does.
    for relative in products:
        text = (root / relative).read_text(encoding="utf-8")
        (root / relative).write_text(text, encoding="utf-8", newline="\n")
    monkeypatch.setattr(normalize, "normalize_corpus", original_normalize)
    monkeypatch.setattr(recovery, "recover_holdout", repaired)
    return module


def test_recovery_replay_distinguishes_original_failure_from_repaired_pass(tmp_path, monkeypatch):
    root = tmp_path / "reference"
    module = _recovery_replay_fixture(root, monkeypatch)
    result = module.replay_recovery(root, tmp_path / "work")
    assert result["original_frozen_evaluation"]["status"] == "failed_reproduced"
    assert result["repaired_reproduction"]["status"] == "passed"
    assert result["repaired_reproduction"]["untouched_holdout_claim"] is False
    assert result["recovery_receipt_matches_published"] is True


@pytest.mark.parametrize("failure_mode", ["unexpected_success", "wrong_exception", "changed_output"])
def test_recovery_replay_requires_exact_original_failure_without_writes(tmp_path, monkeypatch, failure_mode):
    root = tmp_path / "reference"
    module = _recovery_replay_fixture(root, monkeypatch, failure_mode=failure_mode)
    before = (root / "data/processed/holdout_facts.jsonl").read_bytes()
    with pytest.raises(ValueError):
        module.replay_recovery(root, tmp_path / "work")
    assert (root / "data/processed/holdout_facts.jsonl").read_bytes() == before


@pytest.mark.parametrize("repair_mode", ["changed_output", "false_untouched_claim"])
def test_recovery_replay_rejects_changed_products_or_false_untouched_claim(tmp_path, monkeypatch, repair_mode):
    root = tmp_path / "reference"
    module = _recovery_replay_fixture(root, monkeypatch, repair_mode=repair_mode)
    before = (root / "data/processed/holdout_facts.jsonl").read_bytes()
    with pytest.raises(ValueError):
        module.replay_recovery(root, tmp_path / "work")
    assert (root / "data/processed/holdout_facts.jsonl").read_bytes() == before
