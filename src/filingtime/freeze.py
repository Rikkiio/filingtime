"""A verifiable pre-evaluation rule freeze, with honest post-freeze change detection."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RULE_PATHS = (
    "src/filingtime/models.py",
    "src/filingtime/engine.py",
    "src/filingtime/normalize.py",
    "src/filingtime/xbrl.py",
    "src/filingtime/ingest.py",
    "src/filingtime/experiment.py",
    "src/filingtime/_vendor/sec_transform/__init__.py",
    "src/filingtime/_vendor/sec_transform/text2num.py",
    "data/manifests/sec_transform_vendor.json",
    "data/manifests/collection_protocol.json",
    "data/universe.csv",
    "docs/PROTOCOL.md",
    "docs/PROTOCOL_AMENDMENT_01.md",
    "uv.lock",
)


def _hashes(root: Path) -> dict[str, str]:
    result = {}
    for relative in RULE_PATHS:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"Cannot freeze: missing {relative}")
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def freeze_rules(root: str | Path, validation_receipt: str | Path) -> dict:
    root = Path(root).resolve()
    destination = root / "data/manifests/rule_freeze.json"
    if destination.exists():
        raise FileExistsError("Preserve the original rule freeze; do not overwrite it")
    receipt_path = Path(validation_receipt).resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "passed":
        raise ValueError("Development validation receipt must have status=passed")
    if list((root / "data/processed").glob("*holdout*")):
        raise ValueError("Holdout processed files already exist; cannot claim an untouched freeze")
    for parsed in (root / "data/manifests/parsed").glob("*.json"):
        record = json.loads(parsed.read_text(encoding="utf-8"))
        if record.get("split") == "holdout":
            raise ValueError("Holdout filings were already parsed; cannot claim an untouched freeze")
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    result = {
        "protocol": "FilingTime-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": proc.stdout.strip() if proc.returncode == 0 else None,
        "rule_hashes": _hashes(root),
        "source_manifest_hashes": {
            relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
            for relative in ("data/manifests/sources.jsonl", "data/manifests/filings.jsonl")
            if (root / relative).is_file()
        },
        "development_receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "development_receipt": str(receipt_path.relative_to(root)).replace("\\", "/"),
        "holdout_status": "not_parsed_or_inspected_at_freeze",
        "policy": "Any changed rule is disclosed; post-evaluation fixes do not retain untouched status.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def check_freeze(root: str | Path) -> dict:
    root = Path(root).resolve()
    path = root / "data/manifests/rule_freeze.json"
    if not path.exists():
        return {"status": "missing", "changed": [], "claim": "No frozen evaluation rules"}
    record = json.loads(path.read_text(encoding="utf-8"))
    current = _hashes(root)
    changed = [key for key, value in record["rule_hashes"].items() if current.get(key) != value]
    for relative, expected in record.get("source_manifest_hashes", {}).items():
        candidate = root / relative
        if not candidate.exists() or hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            changed.append(relative)
    return {
        "status": "unchanged" if not changed else "changed",
        "changed": changed,
        "freeze_created_at": record["created_at"],
        "claim": "Rule bytes match the pre-evaluation record" if not changed else
                 "Rules changed after freeze; do not present this as an untouched evaluation",
    }
