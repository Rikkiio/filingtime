"""Unit examples use deliberately synthetic records, never simulated SEC evidence."""

from dataclasses import replace
from decimal import Decimal

import pytest

from filingtime.engine import RevenueEngine
from filingtime.models import RevenueFact, load_facts, save_facts
from filingtime.store import FactStore


def fact(**changes):
    record = dict(
        cik="1", accession="synthetic-2024", form="10-K",
        period_start="2023-01-01", period_end="2023-12-31", value="120", unit="USD",
        concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        context_id="FY2023", accepted_at="2024-02-01T16:00:00Z",
        source_url="https://example.invalid/synthetic-2024.html", source_sha256="a" * 64,
        fact_id="revenue-2023", basis_id="synthetic-consolidated-revenue-v1",
        status="accepted", retrieved_at="2026-01-01T00:00:00Z",
    )
    record.update(changes)
    return RevenueFact(**record)


def previous(**changes):
    defaults = dict(period_start="2022-01-01", period_end="2022-12-31", value="100",
                    context_id="FY2022", fact_id="revenue-2022")
    defaults.update(changes)
    return fact(**defaults)


def revised(**changes):
    defaults = dict(accession="synthetic-2025", accepted_at="2025-02-01T16:00:00Z",
                    source_url="https://example.invalid/synthetic-2025.html",
                    source_sha256="b" * 64, value="130")
    defaults.update(changes)
    return fact(**defaults)


def test_three_modes_isolate_distinct_lookahead_mechanisms():
    engine = RevenueEngine([fact(), revised()])
    assert engine.query_revenue("1", "2023-12-31", "2024-01-15", mode="pit").status == "missing"
    early = engine.query_revenue("1", "2023-12-31", "2024-01-15", mode="period_end")
    assert early.value == "120" and early.uses_future_information
    assert engine.query_revenue("1", "2023-12-31", "2024-01-15", mode="latest").status == "missing"
    pit = engine.query_revenue("1", "2023-12-31", "2024-03-01")
    latest = engine.query_revenue("1", "2023-12-31", "2024-03-01", mode="latest")
    assert pit.value == "120" and not pit.uses_future_information
    assert latest.value == "130" and latest.uses_future_information


def test_revised_fact_becomes_visible_at_exact_allowed_instant():
    engine = RevenueEngine([fact(), revised()])
    assert engine.query_revenue("1", "2023-12-31", "2025-02-02T15:59:59.999999Z").value == "120"
    assert engine.query_revenue("1", "2023-12-31", "2025-02-02T16:00:00Z").value == "130"


@pytest.mark.parametrize("as_of", [
    "2024-02-02T16:00:00Z", "2024-12-31", "2025-02-02T15:59:59.999999Z",
    "2025-02-02T16:00:00Z", "2025-12-31",
])
def test_period_end_matches_pit_after_first_actual_availability(as_of):
    engine = RevenueEngine([fact(), revised()])
    pit = engine.query_revenue("1", "2023-12-31", as_of)
    timing = engine.query_revenue("1", "2023-12-31", as_of, mode="period_end")
    assert timing.status == pit.status
    assert timing.value == pit.value
    assert timing.fact == pit.fact and timing.evidence == pit.evidence
    assert not timing.uses_future_information
    pit_dict, timing_dict = pit.to_dict(), timing.to_dict()
    for field in ("mode", "effective_at"):
        pit_dict.pop(field)
        timing_dict.pop(field)
    assert timing_dict == pit_dict


def test_period_end_before_first_disclosure_exposes_only_first_event():
    early = RevenueEngine([fact()]).query_revenue("1", "2023-12-31", "2024-01-15", mode="period_end")
    future_segment = revised(fact_id="future-segment", dimensions={"ProductAxis": "ProductA"})
    future_quarter = revised(fact_id="future-quarter", period_start="2023-10-01")
    expanded = RevenueEngine([fact(), revised(), future_segment, future_quarter]).query_revenue(
        "1", "2023-12-31", "2024-01-15", mode="period_end")
    assert expanded.to_dict() == early.to_dict()


def test_period_end_does_not_skip_first_ambiguous_disclosure():
    first = fact(status="ambiguous", reason="first_basis_unproved")
    engine = RevenueEngine([first, revised()])
    early = engine.query_revenue("1", "2023-12-31", "2024-01-15", mode="period_end")
    assert early.status == "ambiguous" and early.fact is None
    assert early.evidence == (first,)


def test_period_end_updates_on_revision_instead_of_retaining_stale_first_value():
    engine = RevenueEngine([fact(), revised()])
    result = engine.query_revenue("1", "2023-12-31", "2025-03-01", mode="period_end")
    assert result.value == "130"
    assert result.effective_at == revised().available_at


def test_period_end_adopts_later_ambiguous_status_without_falling_back():
    engine = RevenueEngine([fact(), revised(status="ambiguous", reason="basis_unproved")])
    result = engine.query_revenue("1", "2023-12-31", "2025-03-01", mode="period_end")
    pit = engine.query_revenue("1", "2023-12-31", "2025-03-01")
    assert result.status == pit.status == "ambiguous"
    assert result.value is None


def test_period_end_never_releases_first_value_before_period_close():
    engine = RevenueEngine([fact(), revised()])
    assert engine.query_revenue("1", "2023-12-31", "2023-12-31T23:59:59Z", mode="period_end").status == "missing"
    assert engine.query_revenue("1", "2023-12-31", "2023-12-31T23:59:59.999999Z", mode="period_end").value == "120"


def test_period_end_growth_uses_revised_pair_at_actual_revision_time():
    prior_revision = revised(period_start="2022-01-01", period_end="2022-12-31",
                             fact_id="revenue-2022", context_id="FY2022", value="110")
    engine = RevenueEngine([fact(), previous(), revised(), prior_revision])
    for as_of in ("2024-03-01", "2025-03-01"):
        pit = engine.query_growth("1", "2023-12-31", as_of)
        timing = engine.query_growth("1", "2023-12-31", as_of, mode="period_end")
        assert timing.status == pit.status == "ok"
        assert timing.growth == pit.growth
        assert timing.previous == pit.previous


def test_period_end_growth_rejects_new_version_without_same_filing_comparative():
    engine = RevenueEngine([fact(), previous(), revised()])
    timing = engine.query_growth("1", "2023-12-31", "2025-03-01", mode="period_end")
    pit = engine.query_growth("1", "2023-12-31", "2025-03-01")
    assert timing.status == pit.status == "rejected"
    assert timing.reason == pit.reason == "no_same_filing_adjacent_annual_predecessor"


def test_missing_query_is_identical_before_future_append():
    before = RevenueEngine([]).query_revenue("1", "2023-12-31", "2023-12-31")
    after = RevenueEngine([fact()]).query_revenue("1", "2023-12-31", "2023-12-31")
    assert before.to_dict() == after.to_dict()


def test_entire_pit_output_unchanged_by_future_dimensional_fact():
    future = revised(dimensions={"axis": "segment"})
    before = RevenueEngine([fact()]).query_revenue("1", "2023-12-31", "2024-03-01")
    after = RevenueEngine([fact(), future]).query_revenue("1", "2023-12-31", "2024-03-01")
    assert before.to_dict() == after.to_dict()


def test_equal_duplicate_tags_preserve_evidence_without_double_counting_value():
    duplicate = fact(fact_id="another-tag", concept="us-gaap:Revenues", context_id="annual2")
    result = RevenueEngine([fact(), duplicate]).query_revenue("1", "2023-12-31", "2024-03-01")
    assert result.status == "ok" and result.number == Decimal(120)
    assert len(result.evidence) == 2


@pytest.mark.parametrize("change", [{"value": "121"}, {"unit": "EUR"}, {"basis_id": "different-basis"}])
def test_conflicting_same_version_values_units_or_bases_are_refused(change):
    result = RevenueEngine([fact(), fact(fact_id="conflict", **change)]).query_revenue("1", "2023-12-31", "2024-03-01")
    assert result.status == "ambiguous" and result.fact is None


def test_ambiguous_candidate_is_not_ignored_to_improve_coverage():
    uncertain = fact(fact_id="uncertain", status="ambiguous", reason="basis_unproved")
    result = RevenueEngine([fact(), uncertain]).query_revenue("1", "2023-12-31", "2024-03-01")
    assert result.status == "ambiguous"


def test_segment_and_quarterly_values_do_not_become_consolidated_annual_revenue():
    segment = fact(fact_id="segment", dimensions={"ProductAxis": "ProductA"}, value="40")
    quarter = fact(fact_id="quarter", period_start="2023-10-01", value="30")
    engine = RevenueEngine([segment, quarter])
    result = engine.query_revenue("1", "2023-12-31", "2024-03-01")
    assert result.status == "missing"
    assert set(result.diagnostics) == {"excluded_dimensional_fact", "excluded_nonannual_period"}


def test_revenue_free_amendment_does_not_erase_prior_revenue():
    # A real amendment with no revenue has no normalized RevenueFact. A nonannual
    # revenue context in an amendment likewise cannot replace annual revenue.
    amendment_quarter = fact(accession="synthetic-amendment", form="10-K/A",
                             fact_id="quarter-only", period_start="2023-10-01",
                             accepted_at="2024-03-01T00:00:00Z")
    result = RevenueEngine([fact(), amendment_quarter]).query_revenue("1", "2023-12-31", "2024-04-01")
    assert result.value == "120"


def test_unresolved_latest_annual_version_does_not_fall_back_to_stale_number():
    uncertain = revised(status="ambiguous", reason="reclassification_unresolved")
    result = RevenueEngine([fact(), uncertain]).query_revenue("1", "2023-12-31", "2025-03-01")
    assert result.status == "ambiguous" and result.value is None


def test_cutoff_is_enforced_for_latest_baseline():
    future = revised(accession="synthetic-2026", accepted_at="2026-01-01T00:00:00Z")
    result = RevenueEngine([fact(), future]).query_revenue("1", "2023-12-31", "2026-03-01", mode="latest")
    assert result.value == "120"


def test_growth_uses_paired_comparatives_in_same_filing():
    result = RevenueEngine([fact(), previous()]).query_growth("1", "2023-12-31", "2024-03-01")
    assert result.status == "ok" and result.number == Decimal("0.2")
    assert result.previous.accession == result.current.fact.accession
    assert result.reason == "same_filing_same_concept_annual_pair"


def test_growth_refuses_different_concepts_even_in_same_statement_basis():
    current = fact(concept_namespace="http://fasb.org/us-gaap/2024")
    prior = previous(concept="us-gaap:SalesRevenueNet", concept_namespace="http://fasb.org/us-gaap/2024")
    result = RevenueEngine([current, prior]).query_growth("1", "2023-12-31", "2024-03-01")
    assert result.status == "rejected"
    assert result.reason == "unproven_cross_concept_comparability"


def test_growth_refuses_same_local_concept_from_different_namespaces():
    current = fact(concept_namespace="http://fasb.org/us-gaap/2024")
    prior = previous(concept_namespace="https://example.invalid/issuer/2024")
    result = RevenueEngine([current, prior]).query_growth("1", "2023-12-31", "2024-03-01")
    assert result.status == "rejected"
    assert result.reason == "unproven_cross_concept_comparability"


def test_growth_accepts_prefix_alias_for_the_same_namespace_and_local_concept():
    current = fact(concept_namespace="http://fasb.org/us-gaap/2024")
    prior = previous(concept="gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                     concept_namespace="http://fasb.org/us-gaap/2024")
    result = RevenueEngine([current, prior]).query_growth("1", "2023-12-31", "2024-03-01")
    assert result.status == "ok" and result.number == Decimal("0.2")


@pytest.mark.parametrize("change,reason", [
    ({"accession": "older-filing"}, "no_same_filing_adjacent_annual_predecessor"),
    ({"unit": "EUR"}, "incomparable_unit_or_accounting_basis"),
    ({"basis_id": "business-before-disposal"}, "incomparable_unit_or_accounting_basis"),
    ({"value": "0"}, "nonpositive_growth_denominator"),
    ({"value": "-2"}, "nonpositive_growth_denominator"),
    ({"period_end": "2022-12-30"}, "no_same_filing_adjacent_annual_predecessor"),
])
def test_growth_refuses_unproved_comparability(change, reason):
    result = RevenueEngine([fact(), previous(**change)]).query_growth("1", "2023-12-31", "2024-03-01")
    assert result.status == "rejected" and result.reason == reason


def test_growth_does_not_substitute_stale_comparative_after_newer_revision():
    result = RevenueEngine([fact(), previous(), revised()]).query_growth("1", "2023-12-31", "2025-03-01")
    assert result.status == "rejected"
    assert result.current.value == "130"


def test_52_and_53_week_annual_periods_are_supported():
    current = fact(period_start="2023-01-01", period_end="2024-01-06")
    prior = previous(period_start="2022-01-02", period_end="2022-12-31")
    result = RevenueEngine([current, prior]).query_growth("1", "2024-01-06", "2024-03-01")
    assert result.status == "ok"


def test_jsonl_round_trip_preserves_decimal_and_provenance(tmp_path):
    original = fact(value="12345678901234567890.125")
    path = tmp_path / "facts.jsonl"
    save_facts(path, [original])
    assert load_facts(path) == [original]


def test_parquet_store_is_append_only_idempotent_and_decimal_exact(tmp_path):
    store = FactStore(tmp_path / "facts")
    first = fact(value="12345678901234567890.125")
    part = store.append([first])
    assert part is not None and part.exists()
    original_bytes = part.read_bytes()
    assert store.append([first]) is None
    store.append([revised()])
    assert part.read_bytes() == original_bytes
    assert first in store.load()
    assert store.receipt()["fact_count"] == 2


def test_parquet_store_refuses_replacement_even_inside_a_single_batch(tmp_path):
    store = FactStore(tmp_path)
    with pytest.raises(ValueError, match="replacement"):
        store.append([fact(), replace(fact(), value="999")])
    assert not store.parts
    store.append([fact()])
    with pytest.raises(ValueError, match="replacement"):
        store.append([replace(fact(), value="999")])
    assert store.load() == [fact()]


@pytest.mark.parametrize("field,value", [
    ("accepted_at", "2024-02-01"),
    ("accepted_at", "2024-02-01T16:00:00"),
    ("available_at", "2024-02-01T16:00:00Z"),
    ("available_at", "2024-02-03T16:00:00Z"),
    ("retrieved_at", "2026-01-01"),
])
def test_recorded_instants_and_fixed_availability_policy_are_enforced(field, value):
    with pytest.raises(ValueError):
        fact(**{field: value})


def test_acceptance_offset_is_converted_without_changing_instant():
    original = fact(accepted_at="2024-02-01T11:00:00-05:00")
    assert original.accepted_at == "2024-02-01T16:00:00Z"
    assert original.available_at == "2024-02-02T16:00:00Z"


def test_nonfinite_and_binary_float_values_are_rejected():
    for value in ("NaN", "Infinity"):
        with pytest.raises(ValueError):
            fact(value=value)
    with pytest.raises(TypeError):
        fact(value=0.1)


def test_unknown_fields_do_not_silently_drop_provenance():
    with pytest.raises(ValueError, match="Unknown"):
        RevenueFact.from_dict({**fact().to_dict(), "source_sha": "incorrect-field"})
