"""Explicit post-evaluation metadata repair, preserving the failed frozen run.

This is a new, disclosed annotation path. Its outputs are not an untouched
holdout result even though the original frozen computational rules are unchanged.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from lxml import html

from .freeze import RULE_PATHS, check_freeze
from .normalize import normalize_corpus


PRODUCTS = tuple(f"data/processed/holdout_{suffix}" for suffix in
                 ("facts.jsonl", "normalization.json", "targets.json"))
CORRECTIONS = "data/reference/metadata_corrections.json"
FIRST_FAILURE = "data/manifests/holdout_first_evaluation.json"
RECEIPT = "data/manifests/holdout_recovery.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Recovery evidence is missing or outside the repository: {relative}")
    return path


def recover_holdout(root: str | Path, work_dir: str | Path, *, publish: bool = False) -> dict:
    """Apply documented annotations in a new copy, never alter original audits.

    publish=False writes only under work_dir. publish=True additionally saves
    the derived products and receipt, refusing to overwrite different bytes.
    """
    root, work_dir = Path(root).resolve(), Path(work_dir).resolve()
    if work_dir == root or work_dir.is_relative_to(root / "data"):
        raise ValueError("Recovery work must be separate from committed data")
    freeze = check_freeze(root)
    if freeze["status"] != "unchanged":
        raise ValueError("Recovery requires the original frozen rules to remain unchanged")
    failure_path = _input(root, FIRST_FAILURE)
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    if (failure.get("status") != "failed_closed"
            or failure.get("freeze_record_sha256") != _sha(root / "data/manifests/rule_freeze.json")
            or any(failure.get("outputs_existed_before", {}).values())
            or any(failure.get("outputs_exist_after", {}).values())):
        raise ValueError("Recovery requires the preserved initial failure before derived outputs")
    registry_path = _input(root, CORRECTIONS)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if (registry.get("schema_version") != 1
            or registry.get("created_after_first_evaluation") is not True
            or registry.get("untouched_holdout_claim") is not False
            or registry.get("human_review_status") != "pending"):
        raise ValueError("Correction registry must explicitly identify post-evaluation AI annotation")
    corrections = registry.get("corrections", [])
    if not corrections:
        raise ValueError("No explicit correction evidence")
    sources = {row["url"]: row for row in
               (json.loads(line) for line in (root / "data/manifests/sources.jsonl").read_text(encoding="utf-8").splitlines())}
    verified, seen = [], set()
    for correction in corrections:
        accession = correction["accession"]
        if accession in seen or correction.get("field") != "fiscal_year_focus":
            raise ValueError("Only one explicit fiscal-year-label correction per filing is supported")
        seen.add(accession)
        expected_relative = f"data/manifests/parsed/{accession}.json"
        if correction["audit_path"] != expected_relative:
            raise ValueError("Correction accession and original audit path differ")
        audit_path = _input(root, expected_relative)
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if (_sha(audit_path) != correction["audit_sha256"]
                or audit["accession"] != accession or audit["split"] != "holdout"
                or audit["fiscal_year_focus"] != correction["original_value"]):
            raise ValueError("Original audit no longer matches correction evidence")
        new_year = correction["corrected_value"]
        if not isinstance(new_year, str) or len(new_year) != 4 or not new_year.isdigit():
            raise ValueError("Corrected fiscal-year label must be an explicit four-digit year")
        evidence = correction.get("evidence", [])
        if not evidence:
            raise ValueError("A correction requires original-source evidence")
        for reference in evidence:
            source = sources.get(reference["source_url"])
            if (source is None or source["local_path"] != reference["archive_path"]
                    or source["sha256"] != reference["sha256"]):
                raise ValueError("Correction source differs from the frozen source manifest")
            raw = gzip.decompress(_input(root, reference["archive_path"]).read_bytes())
            if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
                raise ValueError("Correction source bytes failed verification")
            anchor = reference["anchor"]
            if not anchor.startswith("#") or not reference["expected_text"].strip():
                raise ValueError("Correction requires an original document anchor and excerpt")
            nodes = html.fromstring(raw).xpath("//*[@id=$anchor]", anchor=anchor[1:])
            text = " ".join(" ".join(node.itertext()) for node in nodes)
            if not nodes or " ".join(reference["expected_text"].split()) not in " ".join(text.split()):
                raise ValueError("Correction excerpt does not match the original anchored text")
        verified.append({"accession": accession, "field": correction["field"],
                         "original_value": correction["original_value"], "corrected_value": new_year,
                         "original_audit_sha256": correction["audit_sha256"]})

    work_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="metadata-recovery-", dir=work_dir))
    freeze_record = json.loads((root / "data/manifests/rule_freeze.json").read_text(encoding="utf-8"))
    paths = set(RULE_PATHS) | set(freeze_record["source_manifest_hashes"]) | {"data/manifests/rule_freeze.json"}
    for relative in sorted(paths):
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_input(root, relative), destination)
    for relative in ("data/manifests/parsed", "data/manifests/candidates"):
        shutil.copytree(root / relative, stage / relative)
    for correction in corrections:
        destination = stage / correction["audit_path"]
        audit = json.loads(destination.read_text(encoding="utf-8"))
        audit["fiscal_year_focus"] = correction["corrected_value"]
        destination.write_text(json.dumps(audit, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    normalized = normalize_corpus(stage, "holdout")
    for relative in PRODUCTS:
        path = stage / relative
        # The frozen normalizer uses native text newlines. Canonicalize only
        # these new derived products; original bytes and rules remain intact.
        content = path.read_text(encoding="utf-8")
        path.write_text(content, encoding="utf-8", newline="\n")
    receipt = {
        "status": "passed", "evaluation_status": "post_evaluation_metadata_repaired_replay",
        "original_frozen_evaluation_status": "failed_closed", "untouched_holdout_claim": False,
        "inspection_after_first_holdout_failure": True, "human_review_status": "pending",
        "freeze": freeze, "normalization": normalized, "corrections": verified,
        "input_files": [{"path": relative, "sha256": _sha(_input(root, relative))} for relative in
                        (FIRST_FAILURE, CORRECTIONS, "src/filingtime/recovery.py")],
        "output_files": [{"path": relative, "sha256": _sha(stage / relative)} for relative in PRODUCTS],
        "limitations": "Source text supports this explicit AI annotation; human review is pending. Unchanged frozen code does not make repaired outputs an untouched evaluation.",
    }
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
    outputs = {relative: (stage / relative).read_bytes() for relative in PRODUCTS}
    outputs[RECEIPT] = receipt_bytes
    if publish:
        for relative, content in outputs.items():
            target = root / relative
            if target.exists() and target.read_bytes() != content:
                raise FileExistsError(f"Preserve existing derived artifact: {relative}")
        for relative, content in outputs.items():
            target = root / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(content)
    return {"staging_root": str(stage), "receipt": receipt}
