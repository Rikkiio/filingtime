"""Evaluate hand-specified synthetic scenarios; never an empirical accuracy claim.

Run after installing the package: python scripts/benchmark_injections.py
The scenario expectations below are literals chosen before executing the engine.
Refusals are reported separately and never converted to true negatives.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from filingtime.engine import RevenueEngine
from filingtime.models import RevenueFact
from filingtime.normalize import normalize_filing

ROOT = Path(__file__).resolve().parents[1]


def fact(**changes) -> RevenueFact:
    fields = dict(
        cik="9999999997", accession="synthetic-original", form="10-K",
        period_start="2023-01-01", period_end="2023-12-31", value="120", unit="USD",
        concept="us-gaap:Revenues", context_id="synthetic-annual",
        accepted_at="2024-02-01T12:00:00Z",
        source_url="https://example.invalid/synthetic-original.html",
        source_sha256="d" * 64, fact_id="synthetic-current", status="accepted",
        basis_id="synthetic-consolidated-total",
        reason="synthetic_fixture_not_an_observed_issuer",
    )
    return RevenueFact(**(fields | changes))


def scenarios() -> tuple[list[dict], list[dict]]:
    original = fact()
    changed = fact(accession="synthetic-later", fact_id="synthetic-comparative",
                   accepted_at="2025-02-01T12:00:00Z", value="110")
    unchanged = replace(changed, value="120")
    previous = fact(fact_id="synthetic-previous", context_id="synthetic-previous-annual",
                    period_start="2022-01-01", period_end="2022-12-31", value="100")
    # Dates, labels, expected statuses and selected values are explicit fixtures.
    temporal = [
        dict(id="period_end_before_disclosure", facts=[original], mode="period_end",
             as_of="2023-12-31T23:59:59.999999Z", expected_status="ok",
             expected_leakage=True, expected_value="120"),
        dict(id="latest_future_changed_value", facts=[original, changed], mode="latest",
             as_of="2024-06-01T12:00:00Z", expected_status="ok",
             expected_leakage=True, expected_value="110"),
        dict(id="latest_future_unchanged_value", facts=[original, unchanged], mode="latest",
             as_of="2024-06-01T12:00:00Z", expected_status="ok",
             expected_leakage=True, expected_value="120"),
        dict(id="pit_excludes_future_revision", facts=[original, changed], mode="pit",
             as_of="2024-06-01T12:00:00Z", expected_status="ok",
             expected_leakage=False, expected_value="120"),
        dict(id="pit_exact_availability_boundary", facts=[original], mode="pit",
             as_of="2024-02-02T12:00:00Z", expected_status="ok",
             expected_leakage=False, expected_value="120"),
        dict(id="latest_without_revision", facts=[original], mode="latest",
             as_of="2024-06-01T12:00:00Z", expected_status="ok",
             expected_leakage=False, expected_value="120"),
        dict(id="latest_revision_already_available", facts=[original, changed], mode="latest",
             as_of="2025-02-02T12:00:00Z", expected_status="ok",
             expected_leakage=False, expected_value="110"),
        dict(id="pit_one_second_before_availability", facts=[original], mode="pit",
             as_of="2024-02-02T11:59:59Z", expected_status="missing",
             expected_leakage=None, expected_value=None),
        dict(id="latest_before_original_availability", facts=[original, changed], mode="latest",
             as_of="2024-02-02T11:59:59Z", expected_status="missing",
             expected_leakage=None, expected_value=None),
    ]
    semantic = [
        dict(id="quarter_is_not_annual", operation="revenue",
             facts=[replace(original, period_start="2023-10-01")], expected_status="missing"),
        dict(id="segment_is_not_consolidated", operation="revenue",
             facts=[replace(original, dimensions='{"BusinessSegmentAxis":"WidgetMember"}')],
             expected_status="missing"),
        dict(id="conflicting_duplicate_contexts", operation="revenue",
             facts=[original, replace(original, fact_id="conflict", context_id="other", value="999")],
             expected_status="ambiguous"),
        dict(id="conflicting_units_in_one_version", operation="revenue",
             facts=[original, replace(original, fact_id="euro", unit="EUR")],
             expected_status="ambiguous"),
        dict(id="growth_with_incompatible_unit", operation="growth",
             facts=[original, replace(previous, unit="EUR")], expected_status="rejected"),
        dict(id="growth_with_nonadjacent_prior_period", operation="growth",
             facts=[original, replace(previous, period_start="2021-01-01", period_end="2021-12-31")],
             expected_status="rejected"),
        dict(id="growth_with_zero_denominator", operation="growth",
             facts=[original, replace(previous, value="0")], expected_status="rejected"),
        dict(id="unsupported_unit_at_normalization", operation="normalize_then_revenue",
             facts=[replace(original, unit="shares", status="ambiguous", basis_id="",
                            label="Revenues", concept_namespace="http://fasb.org/us-gaap/2024",
                            statement_role="https://example.invalid/income | Consolidated Statements of Income")],
             expected_status="ambiguous"),
    ]
    return temporal, semantic


def ratio(numerator: int, denominator: int) -> dict:
    return dict(numerator=numerator, denominator=denominator,
                value=numerator / denominator if denominator else None)


def run() -> dict:
    temporal_fixtures, semantic_fixtures = scenarios()
    temporal_rows, semantic_rows = [], []
    counts = Counter({key: 0 for key in ("TP", "FP", "TN", "FN", "unscored_refusal", "unexpected_answer")})
    for scenario in temporal_fixtures:
        result = RevenueEngine(scenario["facts"]).query_revenue(
            "9999999997", "2023-12-31", scenario["as_of"], mode=scenario["mode"])
        expected, observed = scenario["expected_leakage"], result.uses_future_information
        if result.status != "ok":
            outcome = "unscored_refusal"
        elif expected is None:
            outcome = "unexpected_answer"
        else:
            outcome = ("TP" if observed else "FN") if expected else ("FP" if observed else "TN")
        counts[outcome] += 1
        agrees = (result.status == scenario["expected_status"]
                  and result.value == scenario["expected_value"]
                  and (expected is None or (result.status == "ok" and observed == expected)))
        temporal_rows.append({
            **{key: value for key, value in scenario.items() if key != "facts"},
            "facts": [f.to_dict() for f in scenario["facts"]],
            "observed_status": result.status, "observed_value": result.value,
            "observed_leakage": observed if result.status == "ok" else None,
            "observed_reason": result.reason, "outcome": outcome,
            "selected_accession": result.fact.accession if result.fact else None,
            "expectation_matches": agrees,
        })
    for scenario in semantic_fixtures:
        records, ledger = scenario["facts"], None
        if scenario["operation"] == "normalize_then_revenue":
            records, ledger = normalize_filing(records, {
                "accession": "synthetic-original", "ticker": "SYNTHETIC",
                "split": "development", "calculation_edges": [],
            })
        engine = RevenueEngine(records)
        query = engine.query_growth if scenario["operation"] == "growth" else engine.query_revenue
        result = query("9999999997", "2023-12-31", "2024-06-01T12:00:00Z")
        semantic_rows.append({
            **{key: value for key, value in scenario.items() if key != "facts"},
            "facts": [f.to_dict() for f in scenario["facts"]],
            "observed_status": result.status, "observed_reason": result.reason,
            "normalization_ledger": ledger,
            "expectation_matches": result.status == scenario["expected_status"],
        })
    expected_boolean = sum(s["expected_leakage"] is not None for s in temporal_fixtures)
    evaluated_boolean = sum(counts[key] for key in ("TP", "FP", "TN", "FN"))
    return {
        "schema_version": "filingtime-synthetic-injection-benchmark-v1",
        "evidence_type": "synthetic_predeclared_scenario_labels",
        "limitations": [
            "Artificial amounts, entities and dates; not a real issuer sample or human ground truth.",
            "Labels are literal fixture constants authored by an AI validation agent before execution.",
            "Results measure only these named scenarios, not population accuracy or real-world precision/recall.",
            "Refusals never count as true negatives; an unexpected refusal of a labelled case lowers scoring coverage.",
            "Semantic refusal classification is separate from temporal leakage classification.",
        ],
        "human_review_status": "pending",
        "reviewer_agent_id": "/root/validation_design",
        "availability_convention": "acceptance plus 24 elapsed hours",
        "fixture_input_source": "literal scenario constants in scripts/benchmark_injections.py",
        "code_sha256": {
            path: sha256((ROOT / path).read_bytes()).hexdigest()
            for path in ("scripts/benchmark_injections.py", "src/filingtime/models.py",
                         "src/filingtime/engine.py", "src/filingtime/normalize.py")
        },
        "temporal_summary": {
            "scenario_count": len(temporal_rows),
            "expected_positive_scenarios": sum(s["expected_leakage"] is True for s in temporal_fixtures),
            "expected_negative_scenarios": sum(s["expected_leakage"] is False for s in temporal_fixtures),
            "expected_refusal_scenarios": sum(s["expected_leakage"] is None for s in temporal_fixtures),
            "confusion_matrix": {key: counts[key] for key in ("TP", "FP", "TN", "FN")},
            "observed_refusal_count": counts["unscored_refusal"],
            "unexpected_answer_count": counts["unexpected_answer"],
            "labelled_cases_refused": sum(row["expected_leakage"] is not None and row["observed_status"] != "ok" for row in temporal_rows),
            "scoring_coverage": ratio(evaluated_boolean, expected_boolean),
            "synthetic_precision": ratio(counts["TP"], counts["TP"] + counts["FP"]),
            "synthetic_recall_among_scored_cases": ratio(counts["TP"], counts["TP"] + counts["FN"]),
            "expectation_match_count": sum(row["expectation_matches"] for row in temporal_rows),
        },
        "semantic_summary": {
            "scenario_count": len(semantic_rows),
            "expectation_match_count": sum(row["expectation_matches"] for row in semantic_rows),
            "observed_status_counts": dict(sorted(Counter(row["observed_status"] for row in semantic_rows).items())),
        },
        "temporal_scenarios": temporal_rows,
        "semantic_classification_scenarios": semantic_rows,
        "all_expectations_match": all(row["expectation_matches"] for row in temporal_rows + semantic_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/results/synthetic_injection_benchmark.json")
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "temporal_summary": result["temporal_summary"],
                      "semantic_summary": result["semantic_summary"],
                      "all_expectations_match": result["all_expectations_match"]}, sort_keys=True))
    return 0 if result["all_expectations_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
