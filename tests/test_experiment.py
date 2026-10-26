"""Synthetic experiment checks with hand-computed comparisons and ranks."""

import csv
import json
from decimal import Decimal

import pytest

from filingtime.experiment import average_ranks, evaluate, month_end_queries, run_experiment
from filingtime.models import RevenueFact, save_facts


def fact(cik="1", *, value="120", year=2023, revision=False, **changes):
    accession = f"synthetic-{cik}-{'revision' if revision else 'original'}"
    data = dict(
        cik=cik, accession=accession, form="10-K", period_start=f"{year}-01-01", period_end=f"{year}-12-31",
        value=value, unit="USD", concept="us-gaap:Revenues", context_id=f"annual-{year}",
        accepted_at="2025-02-01T00:00:00Z" if revision else "2024-02-01T00:00:00Z",
        source_url=f"https://example.invalid/{accession}", source_sha256=("b" if revision else "a") * 64,
        fact_id=f"revenue-{year}", basis_id=accession + ":synthetic-basis", status="accepted",
    )
    data.update(changes)
    return RevenueFact(**data)


def pair(cik="1", value="120", *, revision=False):
    return [fact(cik, value=value, revision=revision), fact(cik, value="100", year=2022, revision=revision)]


def target(cik="1", *, split="development", year=2023, **changes):
    result = dict(cik=cik, ticker=f"TEST{cik}", fiscal_year=year, period_end=f"{year}-12-31", split=split, accession="synthetic")
    result.update(changes)
    return result


def test_month_end_grid_handles_leap_year_and_fixed_endpoint():
    queries = month_end_queries()
    assert len(queries) == 84
    assert queries[0] == "2019-01-31T23:59:59.999999Z"
    assert queries[-1] == "2025-12-31T23:59:59.999999Z"
    assert "2020-02-29T23:59:59.999999Z" in queries
    assert "2021-02-28T23:59:59.999999Z" in queries


def test_three_modes_have_identical_keys_and_exclude_unfinished_periods():
    result = evaluate(pair(), [target()], "development", query_dates=["2023-11-30", "2023-12-31", "2024-01-31"])
    assert result.summary["query_key_count"] == 2
    assert len(result.observations) == 6
    for mode in ("pit", "period_end", "latest"):
        assert sum(row["mode"] == mode for row in result.observations) == 2
    assert result.summary["modes"]["period_end"]["revenue"]["future_provenance_count"] == 2
    assert result.summary["modes"]["pit"]["revenue"]["usable_count"] == 0


def test_fixed_month_end_includes_period_ending_on_that_day():
    result = evaluate(pair(), [target()], "development")
    row = next(row for row in result.observations
               if row["mode"] == "period_end" and row["as_of"].startswith("2023-12-31"))
    assert row["revenue_status"] == "ok"


def test_paired_denominators_retain_missing_and_refused_keys():
    facts = pair() + pair(value="130", revision=True)
    result = evaluate(facts, [target()], "development", query_dates=["2024-01-31", "2024-02-29"])
    early = result.summary["comparisons_to_pit"]["period_end"]["growth"]
    assert early["total_query_keys"] == 2
    assert early["baseline_only_usable_count"] == 1
    assert early["both_usable_count"] == 1
    assert early["numeric_changed_count"] == 0
    late = result.summary["comparisons_to_pit"]["latest"]["growth"]
    assert late["neither_usable_count"] == 1
    assert late["both_usable_count"] == 1
    assert late["numeric_changed_count"] == 1
    assert late["absolute_difference"]["mean"] == "0.1"


def test_future_source_with_unchanged_value_is_not_numeric_distortion():
    result = evaluate(pair() + pair(revision=True), [target()], "development", query_dates=["2024-03-31"])
    stats = result.summary["comparisons_to_pit"]["latest"]["revenue"]
    assert stats["baseline_future_provenance_in_pairs"] == 1
    assert stats["numeric_changed_count"] == 0
    assert stats["future_provenance_without_numeric_change_count"] == 1


def test_growth_sign_change_and_zero_are_separate_from_magnitude():
    result = evaluate(pair(value="90") + pair(value="100", revision=True), [target()], "development", query_dates=["2024-03-31"])
    stats = result.summary["comparisons_to_pit"]["latest"]["growth"]
    assert stats["direction_changed_count"] == 1
    assert stats["absolute_difference"]["max"] == "0.1"


def test_average_ranks_uses_exact_ties_and_high_value_first():
    assert average_ranks({"a": Decimal("0.2"), "b": Decimal("0.20"), "c": Decimal("0.1")}) == {
        "a": Decimal("1.5"), "b": Decimal("1.5"), "c": Decimal("3")}


def test_rank_sorting_does_not_round_close_decimal_values():
    result = average_ranks({"a": Decimal("0.100000000000000000000000000001"),
                            "b": Decimal("0.100000000000000000000000000002")})
    assert result == {"b": Decimal(1), "a": Decimal(2)}


def test_rank_reversal_matches_hand_calculation():
    facts = pair("1", "120") + pair("1", "110", revision=True) + pair("2", "110") + pair("2", "120", revision=True)
    result = evaluate(facts, [target("1"), target("2")], "development", query_dates=["2024-03-31"])
    group = next(row for row in result.rankings if row["baseline"] == "latest" and row["record_type"] == "group")
    assert group["candidate_count"] == group["common_count"] == 2
    assert group["changed_members"] == 2
    assert group["mean_absolute_rank_shift"] == "1"
    members = [row for row in result.rankings if row["baseline"] == "latest" and row["record_type"] == "member"]
    assert [row["rank_shift"] for row in members] == ["1", "-1"]


def test_rankings_use_common_set_and_report_excluded_member():
    # Firm 3 has a later current value but no same-filing prior-year comparative:
    # PIT growth is valid while latest growth is refused.
    facts = pair("1") + pair("2", "110") + pair("3", "115") + [fact("3", value="130", revision=True)]
    result = evaluate(facts, [target(str(i)) for i in range(1, 4)], "development", query_dates=["2024-03-31"])
    group = next(row for row in result.rankings if row["baseline"] == "latest" and row["record_type"] == "group")
    assert group["candidate_count"] == group["pit_usable_count"] == 3
    assert group["baseline_usable_count"] == group["common_count"] == 2
    stats = result.summary["comparisons_to_pit"]["latest"]["growth"]
    assert stats["pit_only_usable_count"] == 1 and stats["both_usable_count"] == 2


def test_insufficient_common_group_remains_in_output():
    result = evaluate(pair(), [target()], "development", query_dates=["2024-03-31"])
    assert len(result.rankings) == 2
    assert all(row["status"] == "insufficient_common_members" for row in result.rankings)
    assert result.summary["rankings"]["latest"]["evaluated_groups"] == 0
    assert result.summary["rankings"]["latest"]["rank_change_rate"] is None


def test_empty_inputs_have_explicit_zero_denominators():
    result = evaluate([], [], "development", query_dates=["2024-03-31"])
    assert result.observations == result.rankings == []
    assert result.summary["modes"]["pit"]["revenue"]["coverage"] is None
    assert result.summary["comparisons_to_pit"]["latest"]["growth"]["absolute_difference"]["mean"] is None


def test_duplicate_targets_and_mixed_splits_are_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate(pair(), [target(), target()], "development")
    with pytest.raises(ValueError, match="different splits"):
        evaluate(pair(), [target(split="holdout")], "development")


def test_input_permutation_does_not_change_experiment():
    facts = pair("1") + pair("2", "110")
    targets = [target("1"), target("2")]
    assert evaluate(facts, targets, "development") == evaluate(reversed(facts), reversed(targets), "development")


def test_run_outputs_are_byte_deterministic_and_no_large_evidence_objects(tmp_path):
    processed = tmp_path / "data/processed"
    processed.mkdir(parents=True)
    save_facts(processed / "development_facts.jsonl", pair())
    (processed / "development_targets.json").write_text(json.dumps([target()]), encoding="utf-8")
    first = run_experiment(tmp_path, "development")
    outputs = {p.name: p.read_bytes() for p in (tmp_path / "data/results").iterdir()}
    second = run_experiment(tmp_path, "development")
    assert first == second
    assert outputs == {p.name: p.read_bytes() for p in (tmp_path / "data/results").iterdir()}
    with (tmp_path / "data/results/development_observations.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and "revenue_identity" in rows[0]
    assert "evidence" not in rows[0] and "source_url" not in rows[0]


def test_future_append_keeps_each_pit_observation_unchanged():
    before = evaluate(pair(), [target()], "development", query_dates=["2024-03-31"])
    after = evaluate(pair() + pair(value="130", revision=True), [target()], "development", query_dates=["2024-03-31"])
    assert [row for row in before.observations if row["mode"] == "pit"] == [row for row in after.observations if row["mode"] == "pit"]


def test_direct_holdout_run_requires_rule_freeze(tmp_path):
    with pytest.raises(ValueError, match="unchanged frozen rules"):
        run_experiment(tmp_path, "holdout")
