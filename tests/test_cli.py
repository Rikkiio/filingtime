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
    freeze = root / "data/manifests/rule_freeze.json"
    freeze.parent.mkdir(parents=True, exist_ok=True)
    freeze.write_text(json.dumps({"created_at": "synthetic-test-only", "rule_hashes": hashes}), encoding="utf-8")
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
