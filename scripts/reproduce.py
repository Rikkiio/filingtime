"""Verify the delivered corpus without changing its reference outputs.

Default: all tests, archive/provenance/freeze checks, disclosed recovery replay,
experiment and report replays,
CLI boundaries, immutable Parquet round-trip, one offline Arelle replay, and an
offline wheel build/install smoke test. --reparse replays every original filing.
Dependency installation is a separate earlier `uv sync --frozen` step.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import venv
import xml.etree.ElementTree as ET

from filingtime.audit import coverage_report, verify_corpus, verify_fact_provenance, verify_support_files
from filingtime.experiment import run_experiment
from filingtime.freeze import RULE_PATHS, check_freeze
from filingtime.ingest import load_jsonl
from filingtime.models import load_facts
from filingtime.store import FactStore


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stdout[-12000:]}\n{result.stderr[-12000:]}")
    return result


@contextmanager
def no_network():
    """Make accidental Python network use fail instead of silently completing."""
    def denied(*_args, **_kwargs):
        raise RuntimeError("Network access is forbidden during offline corpus replay")
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create = socket.create_connection
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create


def verify_inputs(root: Path) -> tuple[dict, list]:
    facts = []
    for split in ("development", "holdout"):
        facts_path = root / f"data/processed/{split}_facts.jsonl"
        targets_path = root / f"data/processed/{split}_targets.json"
        if not facts_path.is_file() or not targets_path.is_file():
            raise ValueError(f"Incomplete release inputs for {split}")
        subset = load_facts(facts_path)
        if not subset or not json.loads(targets_path.read_text(encoding="utf-8")):
            raise ValueError(f"Empty release inputs for {split}")
        facts.extend(subset)
    results = {"corpus": verify_corpus(root), "provenance": verify_fact_provenance(root, facts),
               "support_files": verify_support_files(root), "freeze": check_freeze(root),
               "coverage": coverage_report(root)}
    for name in ("corpus", "provenance", "support_files"):
        if results[name]["status"] != "passed":
            raise ValueError(f"{name} check failed: {json.dumps(results[name])}")
    if results["freeze"]["status"] != "unchanged":
        raise ValueError("The release does not match its frozen evaluation rules")
    for split, expected in (("development", 48), ("holdout", 24)):
        coverage = results["coverage"][split]
        if coverage["planned_company_years"] != expected or coverage["identified_target_company_years"] != expected:
            raise ValueError(f"Incomplete {split} target coverage: expected {expected} company-years")
        if coverage["missing_company_years"] or coverage["unparsed_accessions"] or not coverage["collected_filings"]:
            raise ValueError(f"Incomplete {split} source/parse coverage: {json.dumps(coverage)}")
    return results, facts


def check_public_source_hygiene(root: Path) -> dict:
    """Check project-authored text only; public SEC originals are out of scope."""
    extensions = {".py", ".md", ".toml", ".yml", ".yaml", ".txt"}
    paths = {path for path in root.iterdir() if path.is_file() and path.suffix in extensions
             and path.name not in {"LICENSE", "NOTICE"}}
    for relative in ("src", "scripts", "tests", "docs", ".github"):
        directory = root / relative
        if directory.exists():
            paths.update(path for path in directory.rglob("*") if path.is_file() and path.suffix in extensions
                         and "_vendor" not in path.parts)
    checks = {
        "personal_email_address": re.compile(r"[A-Z0-9._%+-]+@(?:gmail|outlook|hotmail|live|qq|163|126|icloud|yahoo)\.(?:com|cn|net)", re.I),
        "machine_specific_drive_path": re.compile(r"\b[DF]:[\\/]", re.I),
        "github_token_shape": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
        "private_key_header": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    }
    findings = []
    for path in sorted(paths):
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            for category, pattern in checks.items():
                if pattern.search(line):
                    findings.append({"path": path.relative_to(root).as_posix(), "line": number, "category": category})
    if findings:
        # Deliberately omit the matched values from logs and receipts.
        raise ValueError(f"Project-authored public source hygiene check failed: {json.dumps(findings)}")
    return {"status": "passed", "files_checked": len(paths),
            "scope": "Project-authored source/docs/tests/workflows; personal-provider email, local drive paths, GitHub token shapes, private-key headers. SEC public originals and third-party vendor text are excluded. This is not an exhaustive secret audit."}


def replay_experiments(root: Path, work: Path) -> dict:
    """Generate into a separate root, leaving even mismatched baselines untouched."""
    staging = work / "experiment-replay"
    staging.mkdir(parents=True, exist_ok=True)
    relatives = list(RULE_PATHS) + ["data/manifests/rule_freeze.json"]
    freeze_record = json.loads((root / "data/manifests/rule_freeze.json").read_text(encoding="utf-8"))
    relatives += list(freeze_record.get("source_manifest_hashes", {}))
    relatives += [f"data/processed/{split}_{kind}" for split in ("development", "holdout")
                  for kind in ("facts.jsonl", "targets.json")]
    for relative in relatives:
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
    expected = {}
    for split in ("development", "holdout"):
        for suffix in ("observations.csv", "rankings.csv", "summary.json"):
            relative = f"data/results/{split}_{suffix}"
            reference = root / relative
            if not reference.is_file():
                raise ValueError(f"Missing committed result artifact: {relative}")
            expected[relative] = digest(reference)
    for split in ("development", "holdout"):
        run_experiment(staging, split)
    mismatches = [relative for relative, checksum in expected.items() if digest(staging / relative) != checksum]
    baseline_changed = [relative for relative, checksum in expected.items() if digest(root / relative) != checksum]
    if mismatches or baseline_changed:
        raise ValueError(f"Experiment replay mismatch; baselines were not overwritten. Different outputs={mismatches}, changed baselines={baseline_changed}")
    return {"status": "passed", "artifact_count": len(expected), "reference_sha256": expected,
            "comparison": "Byte-identical generation in a separate directory; original references unchanged"}


def _tree_hashes(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): digest(path)
            for path in sorted(directory.rglob("*")) if path.is_file()} if directory.exists() else {}


def _recovery_protected_hashes(root: Path, products: tuple[str, ...]) -> dict[str, str]:
    paths = set(RULE_PATHS) | set(products) | {
        "data/manifests/sources.jsonl", "data/manifests/filings.jsonl",
        "data/manifests/rule_freeze.json", "data/manifests/holdout_first_evaluation.json",
        "data/manifests/holdout_recovery.json", "data/reference/metadata_corrections.json",
        "src/filingtime/recovery.py",
    }
    for relative in ("data/raw", "data/manifests/parsed", "data/manifests/candidates"):
        paths.update((Path(relative) / name).as_posix() for name in _tree_hashes(root / relative))
    return {relative: digest(root / relative) for relative in sorted(paths)}


def replay_recovery(root: Path, work: Path) -> dict:
    """Reproduce the original failure, then independently reproduce its repair.

    The unchanged frozen rules are not reinterpreted as a successful untouched
    holdout. Original data and published repaired products remain read-only.
    """
    from filingtime.normalize import normalize_corpus
    from filingtime.recovery import recover_holdout
    products = tuple(f"data/processed/holdout_{suffix}" for suffix in
                     ("facts.jsonl", "normalization.json", "targets.json"))
    first_path = root / "data/manifests/holdout_first_evaluation.json"
    first = json.loads(first_path.read_text(encoding="utf-8"))
    if first.get("status") != "failed_closed" or not first.get("failure"):
        raise ValueError("Recovery replay requires the preserved original failed evaluation")
    if first.get("freeze_record_sha256") != digest(root / "data/manifests/rule_freeze.json"):
        raise ValueError("The first failure does not identify the preserved freeze record")
    for audit in first.get("conflicting_original_audits", []):
        if digest(root / audit["path"]) != audit["sha256"]:
            raise ValueError("Original conflicting audit bytes differ from the first failure receipt")
    protected = _recovery_protected_hashes(root, products)
    failure_stage = work / "original-failure-replay"
    failure_stage.mkdir(parents=True, exist_ok=True)
    freeze_record = json.loads((root / "data/manifests/rule_freeze.json").read_text(encoding="utf-8"))
    inputs = set(RULE_PATHS) | set(freeze_record.get("source_manifest_hashes", {})) | set(products) | {"data/manifests/rule_freeze.json"}
    for relative in sorted(inputs):
        target = failure_stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    for relative in ("data/manifests/parsed", "data/manifests/candidates"):
        shutil.copytree(root / relative, failure_stage / relative, dirs_exist_ok=True)
    before_failed_outputs = _tree_hashes(failure_stage / "data/processed")
    observed_failure = None
    with no_network():
        try:
            normalize_corpus(failure_stage, "holdout")
        except Exception as error:
            observed_failure = {"exception": type(error).__name__, "message": str(error)}
    if _tree_hashes(failure_stage / "data/processed") != before_failed_outputs:
        raise ValueError("Original normalization failure changed or created derived output bytes")
    if observed_failure != first["failure"]:
        raise ValueError(f"Original frozen failure did not reproduce exactly: expected={first['failure']}, observed={observed_failure}")
    with no_network():
        replayed = recover_holdout(root, work / "metadata-recovery-replay", publish=False)
    repaired_stage = Path(replayed["staging_root"]).resolve()
    if not repaired_stage.is_relative_to(work.resolve()) or repaired_stage == root.resolve():
        raise ValueError("Recovery replay did not stay inside isolated scratch storage")
    receipt = replayed["receipt"]
    labels = {
        "status": "passed", "evaluation_status": "post_evaluation_metadata_repaired_replay",
        "original_frozen_evaluation_status": "failed_closed", "untouched_holdout_claim": False,
        "inspection_after_first_holdout_failure": True, "human_review_status": "pending",
    }
    if any(receipt.get(key) != value for key, value in labels.items()):
        raise ValueError("Recovery receipt does not explicitly disclose post-evaluation repair")
    saved_receipt = json.loads((root / "data/manifests/holdout_recovery.json").read_text(encoding="utf-8"))
    if receipt != saved_receipt:
        raise ValueError("Recovery replay provenance/annotation receipt differs from the published record")
    output_hashes = {}
    for relative in products:
        recovered = repaired_stage / relative
        content = recovered.read_bytes()
        content.decode("utf-8")
        if b"\r\n" in content:
            raise ValueError(f"Recovery output is not canonical UTF-8/LF: {relative}")
        checksum = digest(recovered)
        if checksum != protected[relative]:
            raise ValueError(f"Repaired output mismatch; published baseline was not overwritten: {relative}")
        output_hashes[relative] = checksum
    if _recovery_protected_hashes(root, products) != protected:
        raise ValueError("Recovery replay changed original source/audit/freeze or published derived bytes")
    return {
        "status": "passed",
        "original_frozen_evaluation": {"status": "failed_reproduced", "failure": observed_failure,
                                       "derived_outputs_unchanged": True},
        "repaired_reproduction": {"status": "passed", "evaluation_status": labels["evaluation_status"],
                                  "untouched_holdout_claim": False, "artifact_count": len(products),
                                  "output_sha256": output_hashes},
        "protected_original_file_count": len(protected),
        "protected_manifest_sha256": hashlib.sha256(json.dumps(protected, sort_keys=True).encode()).hexdigest(),
        "recovery_receipt_matches_published": True, "network": "blocked_at_socket_layer",
        "human_review_status": "pending",
    }


def _verify_generated_figures(staging: Path) -> dict:
    from PIL import Image
    png = staging / "docs/assets/research_summary.png"
    svg = staging / "docs/assets/research_summary.svg"
    with Image.open(png) as rendered:
        if rendered.format != "PNG":
            raise ValueError("Report figure is not a PNG image")
        rendered.verify()
    with Image.open(png) as rendered:
        width, height = rendered.size
        if width < 640 or height < 360:
            raise ValueError("Report PNG dimensions are too small for the declared figure")
        if not any(low < high for low, high in rendered.convert("RGB").getextrema()):
            raise ValueError("Report PNG is a blank uniform image")
    vector = ET.parse(svg).getroot()
    if vector.tag != "{http://www.w3.org/2000/svg}svg" or len(vector) == 0:
        raise ValueError("Report SVG is empty or has the wrong document root")
    box = [float(value) for value in vector.get("viewBox", "").split()]
    if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
        raise ValueError("Report SVG has no usable viewBox")
    return {
        "png": {"width": width, "height": height, "bytes": png.stat().st_size, "sha256": digest(png)},
        "svg": {"view_box": box, "bytes": svg.stat().st_size, "sha256": digest(svg)},
        "comparison": "Figures must decode, have usable dimensions, and contain content; platform font/rendering differences are not a byte-equality failure.",
    }


def replay_report(root: Path, work: Path) -> dict:
    """Regenerate the report from copied inputs without overwriting references."""
    from filingtime.report import build_report
    artifacts = ("docs/REPORT.md", "data/results/source_coverage.json", "data/results/source_version_changes.csv")
    figures = ("docs/assets/research_summary.png", "docs/assets/research_summary.svg")
    expected = {relative: digest(root / relative) for relative in artifacts}
    original_figures = {relative: digest(root / relative) for relative in figures}
    staging = work / "report-replay"
    staging.mkdir(parents=True, exist_ok=True)

    def ignore_generated(directory: str, names: list[str]) -> set[str]:
        directory_path = Path(directory)
        if directory_path == root / "data/results":
            return set(names) & {"source_coverage.json", "source_version_changes.csv"}
        if directory_path == root / "data/processed":
            return set(names) & {"stores"}
        if directory_path == root / "data":
            return set(names) & {"cache"}
        return set()

    shutil.copytree(root / "data", staging / "data", dirs_exist_ok=True, ignore=ignore_generated)
    for relative in (*RULE_PATHS, "src/filingtime/recovery.py"):
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
    shutil.copytree(root / "src/filingtime/_vendor", staging / "src/filingtime/_vendor", dirs_exist_ok=True)
    # Matplotlib's font cache belongs in explicit scratch storage, not HOME.
    os.environ["MPLCONFIGDIR"] = str(work / "matplotlib-cache")
    with no_network():
        build_report(staging)
    mismatches = [relative for relative, checksum in expected.items()
                  if not (staging / relative).is_file() or digest(staging / relative) != checksum]
    changed_baselines = [relative for relative, checksum in {**expected, **original_figures}.items()
                         if digest(root / relative) != checksum]
    if mismatches or changed_baselines:
        raise ValueError(f"Report replay mismatch; baselines were not overwritten. Different outputs={mismatches}, changed baselines={changed_baselines}")
    rendered = _verify_generated_figures(staging)
    return {"status": "passed", "artifact_count": len(expected), "reference_sha256": expected,
            "figures": rendered, "network": "blocked_at_socket_layer",
            "comparison": "Report Markdown, source coverage and version-change ledger are byte-identical; original text and figure references are unchanged"}


def check_cli(root: Path) -> dict:
    prefix = [sys.executable, "-m", "filingtime.cli"]
    demo = json.loads(run(prefix + ["demo", "--root", str(root)], cwd=root).stdout)
    if demo["before"]["status"] != "missing" or demo["at_availability"]["status"] != "ok":
        raise ValueError("CLI demo did not establish the one-second availability boundary")
    selected = demo["at_availability"]
    query = json.loads(run(prefix + ["query", "--root", str(root), "--cik", selected["cik"],
                                   "--period-end", selected["period_end"], "--as-of", selected["as_of"]], cwd=root).stdout)
    if query != selected:
        raise ValueError("CLI query and demonstration disagree")
    if not demo["biased_period_end"]["uses_future_information"]:
        raise ValueError("Demonstration did not expose the deliberately contaminated baseline")
    return {"status": "passed", "cik": selected["cik"], "period_end": selected["period_end"],
            "source_identity": selected["fact"]["fact_id"], "human_review_status": demo["human_review_status"]}


def check_store(facts: list, work: Path) -> dict:
    store = FactStore(work / "parquet-replay")
    store.append(facts)
    before = store.receipt()
    if store.append(facts) is not None or store.receipt() != before:
        raise ValueError("Identical Parquet re-import was not idempotent")
    loaded = {fact.identity: fact.to_dict() for fact in store.load()}
    expected = {fact.identity: fact.to_dict() for fact in facts}
    if loaded != expected:
        raise ValueError("Parquet round-trip changed a value or its provenance")
    return {"status": "passed", **before}


def check_parser(root: Path, work: Path, reparse_all: bool) -> dict:
    from filingtime.xbrl import parse_filing
    filings = sorted(load_jsonl(root / "data/manifests/filings.jsonl"), key=lambda f: (f["ticker"], f["accepted_at"], f["accession"]))
    if not reparse_all:
        choices = [f for f in filings if f["ticker"] == "AAPL" and f["split"] == "development" and f["is_xbrl"]]
        if not choices:
            raise ValueError("The release lacks the declared Apple parser smoke specimen")
        filings = choices[:1]
    if not filings:
        raise ValueError("No filings selected for parser replay")
    checked = []
    with no_network():
        for filing in filings:
            reference = root / "data/manifests/candidates" / (filing["accession"] + ".jsonl")
            if not reference.is_file():
                raise ValueError(f"Missing parser reference for {filing['accession']}")
            original = load_facts(reference)
            candidates, audit = parse_filing(root, filing, work / "parser-replay", allow_network=False, validate=True)
            expected = {fact.identity: fact.to_dict() for fact in original}
            actual = {fact.identity: fact.to_dict() for fact in candidates}
            if actual != expected:
                missing = sorted(set(expected) - set(actual))
                extra = sorted(set(actual) - set(expected))
                changed = sorted(key for key in set(actual) & set(expected) if actual[key] != expected[key])
                raise ValueError(f"Offline parser replay differs for {filing['accession']}: missing={missing[:5]}, extra={extra[:5]}, changed={changed[:5]}")
            checked.append({"accession": filing["accession"], "candidates": len(candidates), "arelle_errors": audit["arelle_errors"]})
    return {"status": "passed", "scope": "all_filings" if reparse_all else "one_apple_filing", "network": "blocked_at_socket_layer", "filings": checked,
            "claim": "Candidate facts reproduce from fixed source bytes; existing Arelle warnings are disclosed, not erased or treated as human accounting validation"}


def check_wheel(root: Path, work: Path) -> dict:
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("Pinned uv must be available for offline build and install checks")
    wheel_dir = work / "wheel"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    build = run([uv, "build", "--offline", "--wheel", "--out-dir", str(wheel_dir), str(root)], cwd=work)
    wheels = list(wheel_dir.glob("filingtime-*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected exactly one FilingTime wheel")
    clean = work / "installed-wheel"
    venv.EnvBuilder(with_pip=False).create(clean)
    interpreter = clean / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    run([uv, "pip", "install", "--offline", "--python", str(interpreter), "--no-deps", str(wheels[0])], cwd=work, env=env)
    code = "import importlib.metadata,json,filingtime; from filingtime.engine import RevenueEngine; print(json.dumps({'version':importlib.metadata.version('filingtime'),'module':filingtime.__file__,'empty':RevenueEngine([]).query_revenue('1','2023-12-31','2024-01-01').status}))"
    result = json.loads(run([str(interpreter), "-c", code], cwd=work, env=env).stdout)
    if result["empty"] != "missing" or not Path(result["module"]).resolve().is_relative_to(clean.resolve()):
        raise ValueError("The clean interpreter did not execute the installed wheel")
    version = run([str(interpreter), "-m", "filingtime.cli", "--version"], cwd=work, env=env).stdout.strip()
    if version != result["version"]:
        raise ValueError("Installed CLI version mismatch")
    return {"status": "passed", "wheel": wheels[0].name, "sha256": digest(wheels[0]), "version": version,
            "scope": "Offline wheel build, clean no-dependency wheel install, core import/query and CLI version; full dependency integration is exercised by the locked environment checks",
            "build_output": (build.stdout + build.stderr)[-2000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work-dir", type=Path, required=True, help="Writable scratch area outside committed artifacts")
    parser.add_argument("--reparse", action="store_true", help="Offline-parse every filing instead of the Apple smoke specimen")
    args = parser.parse_args()
    root, work_parent = args.root.resolve(), args.work_dir.resolve()
    if work_parent == root or work_parent.is_relative_to(root / "data"):
        parser.error("work-dir must not be the project root or its committed data directory")
    work_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="reproduce-", dir=work_parent))
    temporary = work / "tmp"
    temporary.mkdir()
    os.environ["TMP"] = os.environ["TEMP"] = os.environ["TMPDIR"] = str(temporary)
    # Reuse the cache from the earlier locked installation if supplied. Never
    # create an implicit cache in the user's home while checking the project.
    os.environ.setdefault("UV_CACHE_DIR", str(work_parent / "uv-cache"))
    os.environ.setdefault("PIP_CACHE_DIR", str(work_parent / "pip-cache"))
    os.environ["MPLCONFIGDIR"] = str(work / "matplotlib-cache")
    tempfile.tempdir = str(temporary)
    receipt = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(), "checks": {}}
    started = time.monotonic()
    try:
        print("Checking complete frozen inputs...", flush=True)
        inputs, facts = verify_inputs(root)
        receipt["checks"]["inputs"] = inputs
        receipt["checks"]["public_source_hygiene"] = check_public_source_hygiene(root)
        print("Running all tests...", flush=True)
        tests = run([sys.executable, "-m", "pytest", "-q", "--basetemp", str(work / "pytest")], cwd=root)
        receipt["checks"]["tests"] = {"status": "passed", "output": tests.stdout.strip()}
        for name, function in (
            ("recovery", lambda: replay_recovery(root, work)),
            ("experiments", lambda: replay_experiments(root, work)),
            ("report", lambda: replay_report(root, work)),
            ("cli", lambda: check_cli(root)),
            ("parquet", lambda: check_store(facts, work)),
            ("parser", lambda: check_parser(root, work, args.reparse)),
            ("wheel", lambda: check_wheel(root, work)),
        ):
            print(f"Checking {name}...", flush=True)
            receipt["checks"][name] = function()
        receipt["status"] = "passed"
    except (OSError, ValueError, RuntimeError, ET.ParseError) as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
    destination = work / "reproduction_receipt.json"
    destination.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(destination), "error": receipt.get("error")}, indent=2))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
