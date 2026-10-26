"""Conservative, auditable selection of consolidated annual revenue candidates.

These are source-grounded engineering rules, not independent human accounting
certification. Unknown totals remain ambiguous; excluded components remain in
the normalization ledger rather than becoming fictitious revision events.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import RevenueFact, load_facts, save_facts

MAPPING_VERSION = "consolidated-annual-revenue-v1"
STANDARD_REVENUE = frozenset({
    "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
})
COMPONENT_REVENUE = frozenset({"SalesRevenueGoodsNet", "SalesRevenueServicesNet"})
INCOME = re.compile(r"operations|earnings|income|profit.?and.?loss", re.I)
NON_PRIMARY = re.compile(r"parenthetical|comprehensive|supplement|detail|note", re.I)
NEGATIVE = re.compile(r"cost|expense|deferred|unearned|receivable|liabilit|policy|remainingperformance|percent|per.?share", re.I)
CUSTOM_TOTAL = re.compile(r"^(?:total\s+)?(?:net\s+)?(?:sales\s+and\s+revenues?|revenues?\s+and\s+sales|revenues?|net\s+sales)(?:\s*,?\s*net)?$", re.I)


def primary_income_roles(fact: RevenueFact) -> tuple[str, ...]:
    roles = []
    for role in fact.statement_role.splitlines():
        definition = role.partition(" | ")[2] or role
        if INCOME.search(definition) and not NON_PRIMARY.search(definition):
            if "statement" in definition.lower() or "consolidated" in definition.lower():
                roles.append(role)
    return tuple(sorted(set(roles)))


def candidate_kind(fact: RevenueFact) -> str:
    local = fact.concept.split(":")[-1]
    if fact.concept.startswith("us-gaap:") and fact.concept_namespace and not re.fullmatch(
        r"https?://fasb\.org/us-gaap/\d{4}(?:-\d{2}-\d{2})?", fact.concept_namespace
    ):
        return "not_supported_total_revenue"
    if fact.concept.startswith("us-gaap:") and local in COMPONENT_REVENUE:
        return "standard_revenue_component"
    if fact.concept.startswith("us-gaap:") and local in STANDARD_REVENUE:
        return "standard_revenue_concept"
    label = re.sub(r"\s+", " ", fact.label).strip()
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", local)
    if not NEGATIVE.search(local + " " + label) and (CUSTOM_TOTAL.fullmatch(label) or CUSTOM_TOTAL.fullmatch(words)):
        return "extension_revenue_total"
    return "not_supported_total_revenue"


def _root_concept(concepts: set[str], edges: list[dict], roles: set[str]) -> str | None:
    """Use disclosed sum relationships, never the largest numerical value."""
    graphs: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for edge in edges:
        if edge.get("role") not in roles:
            continue
        try:
            if Decimal(str(edge.get("weight", ""))) != 1:
                continue
        except InvalidOperation:
            continue
        parent = edge.get("from") or edge.get("from_concept")
        child = edge.get("to") or edge.get("to_concept")
        if parent and child:
            graphs[edge["role"]][parent].add(child)
    def descendants(graph: dict[str, set[str]], start: str) -> set[str]:
        seen: set[str] = set()
        pending = list(graph[start])
        while pending:
            item = pending.pop()
            if item not in seen:
                seen.add(item)
                pending.extend(graph[item] - seen)
        return seen
    roots = {concept for concept in concepts for graph in list(graphs.values())
             if concepts - {concept} <= descendants(graph, concept)}
    return next(iter(roots)) if len(roots) == 1 else None


def normalize_filing(candidates: list[RevenueFact], audit: dict) -> tuple[list[RevenueFact], dict]:
    admitted: list[RevenueFact] = []
    ledger: list[dict] = []
    groups: dict[str, list[RevenueFact]] = defaultdict(list)
    for fact in candidates:
        reason = None
        if not fact.is_annual:
            reason = "excluded_nonannual_duration"
        elif not fact.is_consolidated:
            reason = "excluded_dimensional_or_segment_context"
        elif not primary_income_roles(fact):
            reason = "excluded_without_primary_income_statement_role"
        elif candidate_kind(fact) == "not_supported_total_revenue" and NEGATIVE.search(fact.concept + " " + fact.label):
            reason = "excluded_known_non_revenue_concept"
        if reason:
            ledger.append({"identity": fact.identity, "concept": fact.concept,
                           "period_end": fact.period_end, "decision": "excluded", "reason": reason})
        else:
            groups[fact.period_end].append(fact)
    edges = audit.get("revenue_calculation_edges", audit.get("calculation_edges", []))
    for period_end, group in sorted(groups.items()):
        concepts = {fact.concept for fact in group}
        role_sets = [{role.partition(" | ")[0] for role in primary_income_roles(fact)} for fact in group]
        roles = set.intersection(*role_sets) if role_sets else set()
        selected_concept = next(iter(concepts)) if len(concepts) == 1 else _root_concept(concepts, edges, roles)
        component_only = all(candidate_kind(fact) == "standard_revenue_component" for fact in group)
        if component_only:
            selected_concept = None
        if selected_concept is None:
            # Duplicate synonyms with identical value still require an explicit
            # semantic decision: numeric equality is not identity of meaning.
            selected = group
            status, reason = "ambiguous", "multiple_revenue_concepts_without_unique_disclosed_total"
            if component_only:
                reason = "revenue_component_not_proven_to_be_entity_total"
        else:
            selected = [fact for fact in group if fact.concept == selected_concept]
            status, reason = "accepted", "primary_statement_consolidated_annual_total"
            if any(candidate_kind(fact) == "not_supported_total_revenue" for fact in selected):
                status, reason = "ambiguous", "unsupported_primary_statement_revenue_concept"
            for fact in group:
                if fact.concept != selected_concept:
                    ledger.append({"identity": fact.identity, "concept": fact.concept,
                                   "period_end": period_end, "decision": "excluded",
                                   "reason": "disclosed_component_of_selected_total"})
        for fact in selected:
            fact_status, fact_reason = status, reason
            if fact.value is None:
                fact_status, fact_reason = "ambiguous", "missing_or_unparseable_revenue_value"
            elif "invalid" in fact.reason or "unparseable" in fact.reason:
                fact_status, fact_reason = "ambiguous", "source_numeric_validation_failed"
            elif fact.unit != "USD":
                fact_status, fact_reason = "ambiguous", "unsupported_or_conflicting_revenue_unit"
            roles = primary_income_roles(fact)
            # Basis identity is a specific income statement in a specific
            # filing, not an assertion of comparability across later filings.
            role_key = "\n".join(roles)
            basis = fact.accession + ":statement:" + hashlib.sha256(role_key.encode()).hexdigest()[:16]
            updated = replace(fact, basis_id=basis, status=fact_status, reason=fact_reason,
                              mapping_version=MAPPING_VERSION,
                              reference_id="rule:" + MAPPING_VERSION)
            admitted.append(updated)
            ledger.append({"identity": fact.identity, "concept": fact.concept,
                           "period_end": period_end, "decision": fact_status,
                           "reason": fact_reason, "basis_id": basis,
                           "source_url": fact.source_url, "evidence_anchor": fact.evidence_anchor})
    return admitted, {
        "accession": audit.get("accession"), "ticker": audit.get("ticker"),
        "split": audit.get("split"), "mapping_version": MAPPING_VERSION,
        "input_candidates": len(candidates), "engine_facts": len(admitted),
        "decisions": dict(Counter(row["decision"] for row in ledger)), "ledger": ledger,
        "human_review_status": "pending", "annotation_origin": "deterministic_source_mapping",
    }


def normalize_corpus(root: str | Path, split: str) -> dict:
    root = Path(root)
    if split not in {"development", "holdout"}:
        raise ValueError("Unknown sample split")
    if split == "holdout":
        from .freeze import check_freeze
        if check_freeze(root)["status"] != "unchanged":
            raise ValueError("Holdout normalization requires unchanged frozen rules")
    facts = []
    ledgers = []
    targets: dict[tuple[str, int], dict] = {}
    for audit_path in sorted((root / "data/manifests/parsed").glob("*.json")):
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit["split"] != split:
            continue
        candidates = load_facts(root / "data/manifests/candidates" / (audit["accession"] + ".jsonl"))
        selected, ledger = normalize_filing(candidates, audit)
        facts.extend(selected)
        ledgers.append(ledger)
        focus = audit.get("fiscal_year_focus")
        end = audit.get("document_period_end") or audit.get("report_date")
        try:
            year = int(focus)
        except (TypeError, ValueError):
            continue
        if 2019 <= year <= 2024 and end:
            key = (audit["cik"], year)
            target = {"cik": audit["cik"], "ticker": audit["ticker"], "fiscal_year": year,
                      "period_end": end, "split": split, "accession": audit["accession"]}
            if key in targets and targets[key]["period_end"] != end:
                raise ValueError(f"Conflicting fiscal-year end: {key}")
            targets.setdefault(key, target)
    out = root / "data/processed"
    out.mkdir(parents=True, exist_ok=True)
    save_facts(out / f"{split}_facts.jsonl", facts)
    (out / f"{split}_normalization.json").write_text(json.dumps(ledgers, indent=2) + "\n", encoding="utf-8")
    (out / f"{split}_targets.json").write_text(json.dumps(list(targets.values()), indent=2) + "\n", encoding="utf-8")
    return {"split": split, "filings": len(ledgers), "facts": len(facts), "targets": len(targets),
            "fact_status": dict(Counter(f.status for f in facts)), "human_review_status": "pending"}
