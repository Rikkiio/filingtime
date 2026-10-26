"""Synthetic end-to-end guards against silently hiding uncertain new revisions.

No issuer or amount in these tests comes from a held-out filing.
"""

from dataclasses import replace

import pytest

from filingtime.engine import RevenueEngine
from filingtime.models import RevenueFact
from filingtime.normalize import normalize_filing


ROLE = "https://example.invalid/role/ConsolidatedIncome"
ROLE_LABEL = ROLE + " | Consolidated Statements of Income"


def candidate(*, unknown=False, accepted_at="2024-02-01T12:00:00Z", accession="synthetic-original", value="100"):
    return RevenueFact(
        cik="9999999991",
        accession=accession,
        form="10-K",
        period_start="2023-01-01",
        period_end="2023-12-31",
        value=value,
        unit="USD",
        concept="issuer:OperatingRevenuesNet" if unknown else "us-gaap:Revenues",
        concept_namespace="https://example.invalid/taxonomy" if unknown else "http://fasb.org/us-gaap/2024",
        context_id="synthetic-consolidated-annual",
        accepted_at=accepted_at,
        source_url=f"https://example.invalid/{accession}.html",
        source_sha256="7" * 64,
        fact_id="synthetic-unknown" if unknown else "synthetic-total",
        label="Operating revenues" if unknown else "Revenue",
        statement_role=ROLE_LABEL,
        status="ambiguous",
        reason="synthetic_unreviewed_fixture",
    )


def audit(edges=()):
    return {"accession": "synthetic", "split": "development", "calculation_edges": list(edges)}


def test_later_unknown_revenue_event_blocks_fallback_to_old_accepted_value():
    old, _ = normalize_filing([candidate()], audit())
    later = candidate(unknown=True, accepted_at="2024-05-01T12:00:00Z", accession="synthetic-revision", value="125")
    new, _ = normalize_filing([later], audit())
    assert new, "An unknown primary-statement revenue event must not disappear"
    engine = RevenueEngine(old + new)
    before = engine.query_revenue(later.cik, later.period_end, "2024-03-01")
    after = engine.query_revenue(later.cik, later.period_end, "2024-06-01")
    assert before.status == "ok" and before.value == "100"
    assert after.status == "ambiguous"
    assert after.value is None
    assert all(fact.accession == "synthetic-revision" for fact in after.evidence)


def test_unknown_standalone_revenue_is_retained_but_never_admitted_as_a_total():
    facts, receipt = normalize_filing([candidate(unknown=True)], audit())
    assert len(facts) == 1
    assert facts[0].status == "ambiguous"
    assert receipt["decisions"].get("ambiguous") == 1


def test_known_total_can_cover_an_unknown_component_with_same_role_positive_edge():
    total, component = candidate(value="150"), candidate(unknown=True, value="50")
    edge = {"from_concept": total.concept, "to_concept": component.concept, "role": ROLE, "weight": "1"}
    facts, _ = normalize_filing([component, total], audit([edge]))
    assert len(facts) == 1
    assert facts[0].concept == total.concept
    assert facts[0].status == "accepted" and facts[0].value == "150"


@pytest.mark.parametrize(
    "role,weight",
    [(ROLE, "-1"), ("https://example.invalid/role/UnrelatedNote", "1")],
)
def test_unknown_candidate_cannot_be_discarded_using_an_unrelated_or_negative_edge(role, weight):
    total, component = candidate(value="150"), candidate(unknown=True, value="50")
    edge = {"from_concept": total.concept, "to_concept": component.concept, "role": role, "weight": weight}
    facts, _ = normalize_filing([component, total], audit([edge]))
    result = RevenueEngine(facts).query_revenue(total.cik, total.period_end, "2024-03-01")
    assert result.status == "ambiguous"
    assert result.value is None


def test_known_cost_concept_is_excluded_without_creating_a_false_revenue_revision():
    old, _ = normalize_filing([candidate()], audit())
    cost = replace(
        candidate(unknown=True, accepted_at="2024-05-01T12:00:00Z", accession="synthetic-later-cost"),
        concept="issuer:CostOfRevenue",
        label="Cost of revenue",
    )
    new, _ = normalize_filing([cost], audit())
    assert new == []
    result = RevenueEngine(old + new).query_revenue(cost.cik, cost.period_end, "2024-06-01")
    assert result.status == "ok" and result.value == "100"
