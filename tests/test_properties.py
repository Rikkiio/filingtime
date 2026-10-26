"""Independent temporal/accounting properties over clearly synthetic records.

These tests do not estimate empirical extraction accuracy. They attempt to refute
the public query contract without calling private selection helpers.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypothesis import given, settings, strategies as st

from filingtime.engine import RevenueEngine
from filingtime.models import RevenueFact


def _fact(value: int, *, suffix: str = "original", accepted: str = "2024-02-01T12:00:00Z") -> RevenueFact:
    return RevenueFact(
        cik="9999999991",
        accession=f"synthetic-{suffix}",
        form="10-K",
        period_start="2023-01-01",
        period_end="2023-12-31",
        value=str(value),
        unit="USD",
        concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        context_id=f"synthetic-context-{suffix}",
        accepted_at=accepted,
        source_url=f"https://example.invalid/synthetic/{suffix}.html",
        source_sha256="a" * 64,
        fact_id=f"synthetic-fact-{suffix}",
        status="accepted",
        basis_id="synthetic-consolidated-usd",
        reason="synthetic_test_fixture_not_empirical_evidence",
    )


@settings(max_examples=60, deadline=None)
@given(
    original=st.integers(min_value=1, max_value=10**14),
    future_values=st.lists(st.integers(min_value=0, max_value=10**14), min_size=1, max_size=8),
)
def test_appending_future_filings_cannot_rewrite_a_past_snapshot(original, future_values):
    base = _fact(original)
    query = "2024-03-01T00:00:00Z"
    before = RevenueEngine([base]).query_revenue(base.cik, base.period_end, query).to_dict()
    later = []
    for index, value in enumerate(future_values):
        acceptance = datetime(2024, 4, 1, 12, tzinfo=timezone.utc) + timedelta(days=index)
        later.append(_fact(value, suffix=f"future-{index}", accepted=acceptance.isoformat()))
    after = RevenueEngine([base, *later]).query_revenue(base.cik, base.period_end, query).to_dict()
    assert after == before


@settings(max_examples=60, deadline=None)
@given(value=st.integers(min_value=0, max_value=10**14), seconds=st.integers(min_value=1, max_value=86400))
def test_pit_never_exposes_a_fact_before_the_availability_boundary(value, seconds):
    fact = _fact(value)
    boundary = datetime(2024, 2, 2, 12, tzinfo=timezone.utc)
    before = (boundary - timedelta(seconds=seconds)).isoformat()
    engine = RevenueEngine([fact])
    result = engine.query_revenue(fact.cik, fact.period_end, before)
    assert result.status == "missing"
    assert result.fact is None
    exact = engine.query_revenue(fact.cik, fact.period_end, boundary.isoformat())
    assert exact.number == Decimal(value)
    assert exact.uses_future_information is False


@settings(max_examples=45, deadline=None)
@given(
    value=st.integers(min_value=1, max_value=10**12),
    order=st.permutations((0, 1, 2, 3)),
)
def test_permutations_and_identical_reimports_do_not_change_the_answer(value, order):
    base = _fact(value)
    later = _fact(value + 1, suffix="revision", accepted="2024-05-01T12:00:00Z")
    unrelated = replace(_fact(9, suffix="other-issuer"), cik="9999999992")
    records = [base, later, unrelated, base]
    expected = RevenueEngine(records).query_revenue(base.cik, base.period_end, "2024-06-01")
    actual = RevenueEngine(records[index] for index in order).query_revenue(
        base.cik, base.period_end, "2024-06-01"
    )
    assert actual.to_dict() == expected.to_dict()
    assert actual.number == Decimal(value + 1)


@settings(max_examples=50, deadline=None)
@given(
    current=st.integers(min_value=0, max_value=10**10),
    previous=st.integers(min_value=1, max_value=10**10),
    scale=st.sampled_from((1, 10, 1000, 1000000)),
)
def test_growth_is_invariant_to_a_common_money_scale(current, previous, scale):
    current_fact = _fact(current)
    previous_fact = replace(
        current_fact,
        period_start="2022-01-01",
        period_end="2022-12-31",
        value=str(previous),
        fact_id="synthetic-prior-fact",
        context_id="synthetic-prior-context",
    )
    baseline = RevenueEngine([current_fact, previous_fact]).query_growth(
        current_fact.cik, current_fact.period_end, "2024-03-01"
    )
    scaled = RevenueEngine(
        [replace(current_fact, value=str(current * scale)), replace(previous_fact, value=str(previous * scale))]
    ).query_growth(current_fact.cik, current_fact.period_end, "2024-03-01")
    assert baseline.status == scaled.status == "ok"
    assert baseline.number == scaled.number


@settings(max_examples=30, deadline=None)
@given(hour_offset=st.integers(min_value=-12, max_value=14))
def test_equivalent_timezone_representations_select_the_same_evidence(hour_offset):
    fact = _fact(123)
    instant = datetime(2024, 2, 2, 12, tzinfo=timezone.utc)
    local_instant = instant.astimezone(timezone(timedelta(hours=hour_offset)))
    engine = RevenueEngine([fact])
    result = engine.query_revenue(fact.cik, fact.period_end, local_instant.isoformat())
    assert result.to_dict() == engine.query_revenue(fact.cik, fact.period_end, instant.isoformat()).to_dict()


@settings(max_examples=35, deadline=None)
@given(value=st.integers(min_value=0, max_value=10**12))
def test_latest_baseline_cannot_invent_original_disclosure_before_it_happened(value):
    first = _fact(value)
    revised = _fact(value + 9, suffix="later", accepted="2024-08-01T00:00:00Z")
    engine = RevenueEngine([first, revised])
    result = engine.query_revenue(first.cik, first.period_end, "2024-01-15", mode="latest")
    assert result.status == "missing"
    assert result.fact is None
    premature = engine.query_revenue(first.cik, first.period_end, "2024-01-15", mode="period_end")
    assert premature.number == Decimal(value)
    assert premature.uses_future_information
