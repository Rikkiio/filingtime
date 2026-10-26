"""Synthetic fault injection, not empirical issuer error-rate measurements."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from filingtime.engine import RevenueEngine
from filingtime.models import RevenueFact


def _fact(**changes) -> RevenueFact:
    fields = dict(
        cik="9999999993",
        accession="synthetic-original",
        form="10-K",
        period_start="2023-01-01",
        period_end="2023-12-31",
        value="120",
        unit="USD",
        concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        context_id="synthetic-annual",
        accepted_at="2024-02-01T12:00:00Z",
        source_url="https://example.invalid/synthetic/original.html",
        source_sha256="b" * 64,
        fact_id="synthetic-current",
        status="accepted",
        basis_id="synthetic-consolidated-total",
        reason="synthetic_test_fixture_not_empirical_evidence",
    )
    fields.update(changes)
    return RevenueFact(**fields)


def _prior(**changes) -> RevenueFact:
    return _fact(
        **dict(
            period_start="2022-01-01",
            period_end="2022-12-31",
            value="100",
            fact_id="synthetic-prior",
            context_id="synthetic-prior-annual",
        )
        | changes
    )


@pytest.mark.parametrize("bad_timestamp", ["2024-02-01", "2024-02-01T12:00:00"])
def test_source_acceptance_needs_an_explicit_timestamp_and_timezone(bad_timestamp):
    with pytest.raises(ValueError):
        _fact(accepted_at=bad_timestamp)


@pytest.mark.parametrize("override", ["2024-02-01T12:00:00Z", "2024-02-02T11:59:59Z", "2024-02-03T12:00:00Z"])
def test_injected_availability_cannot_silently_change_the_frozen_policy(override):
    with pytest.raises(ValueError):
        _fact(available_at=override)


def test_conflicting_value_under_an_existing_identity_is_rejected():
    original = _fact()
    with pytest.raises(ValueError, match="[Ii]mmutable|[Cc]onflicting"):
        RevenueEngine([original, replace(original, value="999")])


def test_conflicting_duplicate_contexts_do_not_depend_on_input_order():
    first = _fact()
    contradiction = replace(first, fact_id="synthetic-conflict", context_id="synthetic-conflict", value="999")
    for records in ([first, contradiction], [contradiction, first]):
        result = RevenueEngine(records).query_revenue(first.cik, first.period_end, "2024-03-01")
        assert result.status == "ambiguous"
        assert result.value is None
        assert {fact.value for fact in result.evidence} == {"120", "999"}


def test_an_unresolved_candidate_prevents_a_false_definitive_answer():
    first = _fact()
    unresolved = replace(first, fact_id="synthetic-unknown", status="ambiguous", value="130", reason="unresolved_custom_concept")
    result = RevenueEngine([first, unresolved]).query_revenue(first.cik, first.period_end, "2024-03-01")
    assert result.status == "ambiguous"
    assert result.fact is None


def test_segment_and_quarterly_injections_are_not_consolidated_annual_revenue():
    original = _fact()
    segment = replace(original, fact_id="synthetic-segment", value="777", dimensions='{"BusinessSegmentAxis":"WidgetMember"}')
    quarter = replace(original, fact_id="synthetic-quarter", value="888", period_start="2023-10-01")
    result = RevenueEngine([quarter, segment, original]).query_revenue(original.cik, original.period_end, "2024-03-01")
    assert result.status == "ok"
    assert result.number == Decimal("120")
    assert "excluded_nonannual_period" in result.diagnostics
    assert "excluded_dimensional_fact" in result.diagnostics


@pytest.mark.parametrize("changed", [{"unit": "EUR"}, {"basis_id": "synthetic-different-operations"}])
def test_incompatible_growth_inputs_are_refused(changed):
    original = _fact()
    result = RevenueEngine([original, _prior(**changed)]).query_growth(original.cik, original.period_end, "2024-03-01")
    assert result.status == "rejected"
    assert result.growth is None
    assert "incomparable" in result.reason


def test_growth_cannot_splice_a_prior_value_from_a_different_filing():
    original = _fact()
    unrelated_prior = _prior(accession="synthetic-other-filing")
    result = RevenueEngine([original, unrelated_prior]).query_growth(original.cik, original.period_end, "2024-03-01")
    assert result.status == "rejected"
    assert result.growth is None


def test_growth_cannot_jump_over_a_missing_fiscal_year():
    original = _fact()
    too_old = _prior(period_start="2021-01-01", period_end="2021-12-31")
    result = RevenueEngine([original, too_old]).query_growth(original.cik, original.period_end, "2024-03-01")
    assert result.status == "rejected"
    assert result.growth is None


def test_zero_growth_denominator_does_not_become_infinite_growth():
    original = _fact()
    result = RevenueEngine([original, _prior(value="0")]).query_growth(original.cik, original.period_end, "2024-03-01")
    assert result.status == "rejected"
    assert result.growth is None
    assert "denominator" in result.reason


def test_normal_later_annual_filing_can_update_an_earlier_comparative():
    original = _fact()
    revised = _fact(
        accession="synthetic-next-annual",
        fact_id="synthetic-revised-comparative",
        value="110",
        accepted_at="2025-02-01T12:00:00Z",
    )
    engine = RevenueEngine([original, revised])
    historical = engine.query_revenue(original.cik, original.period_end, "2024-06-01")
    subsequently = engine.query_revenue(original.cik, original.period_end, "2025-03-01")
    assert historical.number == Decimal("120")
    assert subsequently.number == Decimal("110")
    assert historical.fact.accession == "synthetic-original"
    assert subsequently.fact.form == "10-K"


def test_unchanged_amendment_is_not_a_numeric_change():
    original = _fact()
    amendment = _fact(
        accession="synthetic-amendment",
        fact_id="synthetic-amendment-current",
        form="10-K/A",
        accepted_at="2024-06-01T12:00:00Z",
    )
    engine = RevenueEngine([original, amendment])
    before = engine.query_revenue(original.cik, original.period_end, "2024-03-01")
    after = engine.query_revenue(original.cik, original.period_end, "2024-07-01")
    assert before.number == after.number == Decimal("120")
    assert before.fact.accession != after.fact.accession


def test_same_number_does_not_hide_future_version_provenance():
    original = _fact()
    unchanged_future = _fact(accession="synthetic-future", fact_id="synthetic-future-current", accepted_at="2025-02-01T12:00:00Z")
    engine = RevenueEngine([original, unchanged_future])
    pit = engine.query_revenue(original.cik, original.period_end, "2024-06-01", mode="pit")
    latest = engine.query_revenue(original.cik, original.period_end, "2024-06-01", mode="latest")
    assert pit.number == latest.number
    assert pit.uses_future_information is False
    assert latest.uses_future_information is True


@pytest.mark.parametrize("mode", ["pit", "period_end", "latest"])
def test_post_cutoff_files_cannot_enter_any_experimental_mode(mode):
    original = _fact()
    excluded = _fact(accession="synthetic-outside-cutoff", fact_id="synthetic-2026", value="9999", accepted_at="2026-01-01T00:00:00Z")
    result = RevenueEngine([original, excluded]).query_revenue(original.cik, original.period_end, "2026-03-01", mode=mode)
    assert result.number == Decimal("120")
    assert result.fact.accession == original.accession


def test_a_fiscal_53_week_year_is_valid_without_calendar_year_assumptions():
    current = _fact(period_start="2023-01-01", period_end="2024-01-06")
    result = RevenueEngine([current, _prior()]).query_growth(current.cik, current.period_end, "2024-03-01")
    assert result.status == "ok"
    assert result.number == Decimal("0.2")
