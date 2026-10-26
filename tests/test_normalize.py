"""Adversarial semantic fixtures independent of the corpus's observed outcomes.

All amounts and issuers here are synthetic. These tests evaluate admission rules,
not human-audited accounting accuracy.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from filingtime.engine import RevenueEngine
from filingtime.models import RevenueFact
from filingtime.normalize import normalize_corpus, normalize_filing

MAIN = "https://example.invalid/role/ConsolidatedIncome"
MAIN_ROLE = MAIN + " | Consolidated Statements of Income"
NOTE = "https://example.invalid/role/RevenueNote"


def _candidate(concept="us-gaap:Revenues", value="90", label="Revenue", **changes):
    values = dict(
        cik="9999999994",
        accession="synthetic-normalization",
        form="10-K",
        period_start="2023-01-01",
        period_end="2023-12-31",
        value=value,
        unit="USD",
        concept=concept,
        context_id="synthetic-current-year",
        accepted_at="2024-02-01T12:00:00Z",
        source_url="https://example.invalid/synthetic-normalization.html",
        source_sha256="c" * 64,
        fact_id=concept.replace(":", "-"),
        label=label,
        statement_role=MAIN_ROLE,
        status="ambiguous",
        reason="synthetic_unreviewed_fixture",
    )
    values.update(changes)
    return RevenueFact(**values)


def _audit(edges=()):
    return {
        "accession": "synthetic-normalization",
        "ticker": "SYNTHETIC",
        "split": "development",
        "calculation_edges": list(edges),
    }


def _edge(parent, child, role=MAIN, weight="1"):
    return {"from_concept": parent, "to_concept": child, "role": role, "weight": weight}


def test_declared_total_is_selected_even_when_it_is_not_the_largest_number():
    total = _candidate()
    goods = _candidate("us-gaap:SalesRevenueGoodsNet", "100", "Product revenue")
    services = _candidate("us-gaap:SalesRevenueServicesNet", "-10", "Services revenue")
    edges = [_edge(total.concept, goods.concept), _edge(total.concept, services.concept)]
    normalized, ledger = normalize_filing([services, goods, total], _audit(edges))
    assert len(normalized) == 1
    assert normalized[0].concept == total.concept
    assert normalized[0].value == "90"
    assert normalized[0].status == "accepted"
    assert ledger["decisions"]["excluded"] == 2


def test_unrelated_note_calculation_cannot_choose_the_income_statement_total():
    total = _candidate()
    second = _candidate("us-gaap:SalesRevenueNet", "100", "Net sales")
    normalized, _ = normalize_filing([total, second], _audit([_edge(total.concept, second.concept, NOTE)]))
    assert normalized
    assert all(fact.status != "accepted" for fact in normalized)


def test_a_calculation_chain_cannot_bridge_unrelated_extended_link_roles():
    total = _candidate()
    second = _candidate("us-gaap:SalesRevenueNet", "100", "Net sales")
    edges = [
        _edge(total.concept, "synthetic:Intermediate", MAIN),
        _edge("synthetic:Intermediate", second.concept, NOTE),
    ]
    normalized, _ = normalize_filing([total, second], _audit(edges))
    assert all(fact.status != "accepted" for fact in normalized)


def test_a_custom_local_name_does_not_make_deferred_revenue_a_standard_total():
    candidate = _candidate("issuer:Revenues", "900", "Deferred revenue")
    normalized, ledger = normalize_filing([candidate], _audit())
    assert not any(fact.status == "accepted" for fact in normalized)
    assert ledger["input_candidates"] == 1


@pytest.mark.parametrize(
    "namespace",
    ["https://issuer.invalid/custom/2024", "http://fasb.org.evil.invalid/us-gaap/2024", "http://fasb.org/us-gaap/2024/extension"],
)
def test_a_forged_us_gaap_prefix_cannot_override_its_actual_namespace(namespace):
    candidate = _candidate(concept_namespace=namespace)
    normalized, _ = normalize_filing([candidate], _audit())
    assert not any(fact.status == "accepted" for fact in normalized)


def test_a_real_standard_namespace_retains_the_original_provenance():
    candidate = _candidate(concept_namespace="http://fasb.org/us-gaap/2024")
    normalized, _ = normalize_filing([candidate], _audit())
    assert len(normalized) == 1
    assert normalized[0].status == "accepted"
    assert normalized[0].concept_namespace == candidate.concept_namespace
    assert normalized[0].source_sha256 == candidate.source_sha256


@pytest.mark.parametrize("reason", ["invalid_xbrl_numeric_fact", "unparseable_numeric_candidate"])
def test_a_parse_validation_failure_cannot_be_overwritten_by_a_plausible_number(reason):
    candidate = _candidate(reason=reason)
    normalized, _ = normalize_filing([candidate], _audit())
    assert normalized
    assert all(fact.status != "accepted" for fact in normalized)


def test_a_single_product_component_is_not_automatically_consolidated_total():
    goods = _candidate("us-gaap:SalesRevenueGoodsNet", "100", "Product revenue")
    normalized, _ = normalize_filing([goods], _audit())
    assert not any(fact.status == "accepted" for fact in normalized)


def test_unknown_primary_statement_total_cannot_leave_a_component_as_the_answer():
    goods = _candidate("us-gaap:SalesRevenueGoodsNet", "100", "Product revenue")
    unsupported_total = _candidate("issuer:TotalOperatingRevenue", "125", "Total operating revenue")
    normalized, _ = normalize_filing([goods, unsupported_total], _audit())
    assert not any(fact.status == "accepted" and fact.concept == goods.concept for fact in normalized)


@pytest.mark.parametrize("unit", ["EUR", "USD/shares", "pure", ""])
def test_unsupported_units_remain_explicitly_unresolved(unit):
    normalized, _ = normalize_filing([_candidate(unit=unit)], _audit())
    assert normalized
    assert all(fact.status != "accepted" for fact in normalized)
    assert any("unit" in fact.reason for fact in normalized)


@pytest.mark.parametrize(
    "role",
    [
        "https://example.invalid/role/Details | Revenue Note Details",
        "https://example.invalid/role/Comprehensive | Consolidated Statements of Comprehensive Income",
        "https://example.invalid/role/Parenthetical | Consolidated Statements of Income (Parenthetical)",
        "",
    ],
)
def test_notes_and_other_nonprimary_roles_do_not_establish_the_total(role):
    normalized, ledger = normalize_filing([_candidate(statement_role=role)], _audit())
    assert not normalized
    assert ledger["decisions"] == {"excluded": 1}


def test_a_nonfinancial_amendment_with_no_revenue_facts_cannot_erase_a_value():
    existing, _ = normalize_filing([_candidate()], _audit())
    amendment, ledger = normalize_filing([], _audit())
    assert ledger["input_candidates"] == 0
    assert amendment == []
    result = RevenueEngine(existing + amendment).query_revenue("9999999994", "2023-12-31", "2024-07-01")
    assert result.status == "ok"
    assert result.value == "90"


def test_conflicting_context_values_are_not_silently_resolved_by_normalization():
    first = _candidate()
    conflicting = replace(first, value="901", fact_id="synthetic-contradiction", context_id="synthetic-conflicting-context")
    normalized, _ = normalize_filing([first, conflicting], _audit())
    result = RevenueEngine(normalized).query_revenue(first.cik, first.period_end, "2024-03-01")
    assert result.status == "ambiguous"
    assert result.value is None


@pytest.mark.parametrize("freeze_status", ["missing", "changed"])
def test_holdout_normalization_requires_an_unchanged_rule_freeze(tmp_path, monkeypatch, freeze_status):
    import filingtime.freeze

    monkeypatch.setattr(filingtime.freeze, "check_freeze", lambda root: {"status": freeze_status})
    with pytest.raises(ValueError, match="frozen"):
        normalize_corpus(tmp_path, "holdout")
    assert not (tmp_path / "data/processed").exists()


def test_existing_parsed_holdout_values_prevent_a_claim_of_untouched_freeze(tmp_path):
    from filingtime.freeze import RULE_PATHS, freeze_rules

    for relative in RULE_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic rule content\n", encoding="utf-8")
    parsed = tmp_path / "data/manifests/parsed/already-inspected.json"
    parsed.parent.mkdir(parents=True, exist_ok=True)
    parsed.write_text(json.dumps({"split": "holdout", "status": "parsed"}), encoding="utf-8")
    validation = tmp_path / "development_validation.json"
    validation.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    with pytest.raises(ValueError, match="[Hh]oldout|[Hh]eld.out"):
        freeze_rules(tmp_path, validation)
    assert not (tmp_path / "data/manifests/rule_freeze.json").exists()
