"""Small reproducible command-line interface; no account credentials are needed offline."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from datetime import timedelta
from pathlib import Path

from .models import load_facts, utc_datetime


def _facts(root: Path, split: str = "all") -> list:
    splits = ("development", "holdout") if split == "all" else (split,)
    result = []
    for item in splits:
        path = root / f"data/processed/{item}_facts.jsonl"
        if path.exists():
            store_path = root / f"data/processed/stores/{item}"
            if list(store_path.glob("facts-*.parquet")):
                from .store import FactStore
                stored = FactStore(store_path).load()
                expected = load_facts(path)
                if {f.identity: f.to_dict() for f in stored} != {f.identity: f.to_dict() for f in expected}:
                    raise ValueError("Parquet store differs from normalized evidence; preserve it and build a new versioned store")
                result.extend(stored)
            else:
                result.extend(load_facts(path))
    if not result:
        raise ValueError("No processed facts found. Use the repository corpus and run normalization first.")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FilingTime: evidence-linked historical revenue queries")
    parser.add_argument("--version", action="version", version=importlib.metadata.version("filingtime"))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "verify", "demo", "query", "normalize", "recover-holdout", "experiment", "report", "freeze", "freeze-status", "build-store", "crosscheck"):
        sub = commands.add_parser(name)
        sub.add_argument("--root", type=Path, default=Path.cwd(), help="Path to the FilingTime repository")
        if name in {"query", "normalize", "experiment", "build-store", "crosscheck"}:
            choices = ("development", "holdout", "all") if name == "query" else ("development", "holdout")
            sub.add_argument("--split", choices=choices, default="all" if name == "query" else "development")
        if name == "query":
            sub.add_argument("--cik", required=True)
            sub.add_argument("--period-end", required=True)
            sub.add_argument("--as-of", required=True, help="Aware ISO timestamp, or a UTC end-of-day date")
            sub.add_argument("--mode", choices=("pit", "latest", "period_end"), default="pit")
            sub.add_argument("--growth", action="store_true")
        if name == "freeze":
            sub.add_argument("--receipt", type=Path, required=True)
        if name == "recover-holdout":
            sub.add_argument("--work-dir", type=Path, required=True,
                             help="Scratch space for explicitly disclosed post-evaluation metadata repair")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "doctor":
            result = {"python": sys.version.split()[0], "repository": str(root),
                      "packages": {name: importlib.metadata.version(name) for name in
                                   ("filingtime", "arelle-release", "duckdb", "pyarrow")},
                      "corpus_present": (root / "data/manifests/filings.jsonl").exists(),
                      "human_review_status": "pending"}
        elif args.command == "verify":
            from .audit import verify_corpus, verify_fact_provenance, verify_support_files
            result = {"corpus": verify_corpus(root), "support_files": verify_support_files(root)}
            try:
                result["provenance"] = verify_fact_provenance(root, _facts(root))
            except ValueError as error:
                result["provenance"] = {"status": "failed", "error": str(error)}
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if all(value["status"] == "passed" for value in result.values()) else 1
        elif args.command == "query":
            from .engine import RevenueEngine
            engine = RevenueEngine(_facts(root, args.split))
            query = engine.query_growth if args.growth else engine.query_revenue
            result = query(args.cik, args.period_end, args.as_of, mode=args.mode).to_dict()
        elif args.command == "demo":
            from .engine import RevenueEngine
            facts = _facts(root, "development")
            accepted = [f for f in facts if f.status == "accepted" and f.is_annual and f.is_consolidated
                        and "2019-01-01" <= f.period_end <= "2024-12-31"]
            if not accepted:
                raise ValueError("No accepted development observation available for the demonstration")
            fact = min(accepted, key=lambda f: (f.available_at, f.cik, f.period_end))
            engine = RevenueEngine(facts)
            before = (utc_datetime(fact.available_at) - timedelta(seconds=1)).isoformat()
            result = {"purpose": "Replay the one-second boundary around the declared availability convention",
                      "time_rule": "SEC acceptance plus 24 elapsed hours, not measured market dissemination",
                      "human_review_status": "pending", "source": fact.source_url,
                      "before": engine.query_revenue(fact.cik, fact.period_end, before).to_dict(),
                      "at_availability": engine.query_revenue(fact.cik, fact.period_end, fact.available_at).to_dict(),
                      "biased_period_end": engine.query_revenue(fact.cik, fact.period_end, before, mode="period_end").to_dict()}
        elif args.command == "normalize":
            from .normalize import normalize_corpus
            result = normalize_corpus(root, args.split)
        elif args.command == "recover-holdout":
            from .recovery import recover_holdout
            result = recover_holdout(root, args.work_dir, publish=True)
        elif args.command == "build-store":
            from .store import FactStore
            store = FactStore(root / f"data/processed/stores/{args.split}")
            store.append(load_facts(root / f"data/processed/{args.split}_facts.jsonl"))
            result = store.receipt()
            (store.directory / "receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        elif args.command == "experiment":
            from .experiment import run_experiment
            result = run_experiment(root, args.split)
        elif args.command == "crosscheck":
            from .crosscheck import crosscheck_companyfacts
            result = crosscheck_companyfacts(root, args.split)
        elif args.command == "report":
            from .report import build_report
            result = build_report(root)
        elif args.command == "freeze":
            from .freeze import freeze_rules
            result = freeze_rules(root, args.receipt)
        else:
            from .freeze import check_freeze
            result = check_freeze(root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
