"""Deterministic point-in-time queries and deliberately biased baselines.

Only ``pit`` is historically admissible. ``latest`` deliberately replaces values
with later corpus versions, and ``period_end`` deliberately brings the first
observation forward to the end of its financial period, while retaining the
actual availability of every subsequent version. These are experiments, not
alternative definitions of historically available data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import localcontext
from typing import Iterable

from .models import GrowthResult, QueryResult, RevenueFact, VALID_MODES, decimal_text, iso_date, iso_utc, utc_datetime


class RevenueEngine:
    def __init__(self, facts: Iterable[RevenueFact], *, corpus_cutoff: str = "2025-12-31T23:59:59Z") -> None:
        self.corpus_cutoff = iso_utc(corpus_cutoff)
        cutoff = utc_datetime(self.corpus_cutoff)
        self.facts = tuple(f for f in facts if utc_datetime(f.accepted_at) <= cutoff)
        identities: dict[str, RevenueFact] = {}
        for fact in self.facts:
            if fact.identity in identities and identities[fact.identity] != fact:
                raise ValueError(f"Conflicting records for immutable identity {fact.identity}")
            identities[fact.identity] = fact
        self.facts = tuple(identities.values())

    @staticmethod
    def _resolve(group: list[RevenueFact]) -> tuple[str, str, RevenueFact | None]:
        accepted = [f for f in group if f.status == "accepted"]
        unknown = [f for f in group if f.status == "ambiguous"]
        if unknown:
            return "ambiguous", "unresolved_candidate_in_selected_version", None
        if not accepted:
            return "rejected", "selected_version_has_no_admitted_revenue", None
        signatures = {(f.period_start, f.period_end, f.number, f.unit, f.basis_id) for f in accepted}
        if len(signatures) > 1:
            return "ambiguous", "conflicting_values_or_accounting_bases", None
        chosen = min(accepted, key=lambda f: (f.accession, f.concept, f.context_id, f.fact_id))
        return "ok", "unique_value_and_accounting_basis", chosen

    def query_revenue(self, cik: str, period_end: str, as_of: str, *, mode: str = "pit") -> QueryResult:
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
        cik, period_end, query_time = str(cik).zfill(10), iso_date(period_end), utc_datetime(as_of)
        base = dict(cik=cik, period_end=period_end, as_of=iso_utc(query_time), mode=mode)
        raw = [f for f in self.facts if f.cik == cik and f.period_end == period_end and f.form in {"10-K", "10-K/A"}]
        # Even counts and rejection diagnostics must not reveal future records.
        # With no eligible facts, the reason cannot distinguish a future filing
        # from no filing: that distinction was not knowable at the query time.
        if mode == "pit":
            raw = [f for f in raw if utc_datetime(f.available_at) <= query_time]
        elif mode == "period_end":
            period_close = datetime.combine(date.fromisoformat(period_end), datetime.max.time(), tzinfo=timezone.utc)
            if query_time < period_close:
                return QueryResult(status="missing", reason="financial_period_not_finished", **base)
            annual = [f for f in raw if f.is_annual and f.is_consolidated]
            first_time = min((utc_datetime(f.available_at) for f in annual), default=None)
            if first_time is not None and query_time < first_time:
                # The intentional timing error reveals precisely the first
                # event, not any later version, diagnostic, or candidate count.
                raw = [f for f in raw if utc_datetime(f.available_at) == first_time]
            else:
                raw = [f for f in raw if utc_datetime(f.available_at) <= query_time]
        candidates = [f for f in raw if f.is_annual and f.is_consolidated]
        diagnostics = tuple(sorted({
            *("excluded_nonannual_period" for f in raw if not f.is_annual),
            *("excluded_dimensional_fact" for f in raw if not f.is_consolidated),
        }))
        base.update(candidate_count=len(candidates), diagnostics=diagnostics)
        if not candidates:
            reason = "no_available_consolidated_annual_candidate" if mode == "pit" else "no_consolidated_annual_candidate"
            return QueryResult(status="missing", reason=reason, **base)
        dates = sorted({utc_datetime(f.available_at) for f in candidates})
        if mode == "pit":
            eligible = [t for t in dates if t <= query_time]
            if not eligible:
                return QueryResult(status="missing", reason="not_yet_available", **base)
            selected_time, effective = eligible[-1], eligible[-1]
        elif mode == "latest":
            if query_time < dates[0]:
                return QueryResult(status="missing", reason="not_yet_originally_available", **base)
            selected_time, effective = dates[-1], dates[0]
        else:
            # Shift only the FIRST disclosure event earlier. Keeping that first
            # value forever would confound timing leakage with stale data.
            eligible = [t for t in dates if t <= query_time]
            selected_time = eligible[-1] if eligible else dates[0]
            effective = period_close if selected_time == dates[0] else selected_time
        group = [f for f in candidates if utc_datetime(f.available_at) == selected_time]
        status, reason, selected = self._resolve(group)
        return QueryResult(status=status, reason=reason, fact=selected,
                           evidence=tuple(sorted(group, key=lambda f: (f.accession, f.fact_id))),
                           effective_at=iso_utc(effective), **base)

    def query_growth(self, cik: str, period_end: str, as_of: str, *, mode: str = "pit") -> GrowthResult:
        current = self.query_revenue(cik, period_end, as_of, mode=mode)
        if current.status != "ok" or current.fact is None:
            return GrowthResult(current.status, f"current:{current.reason}", current)
        selected = current.fact
        prior_end = (date.fromisoformat(selected.period_start) - timedelta(days=1)).isoformat()
        prior_candidates = [f for f in self.facts
                            if f.cik == selected.cik and f.accession == selected.accession
                            and f.period_end == prior_end and f.is_annual and f.is_consolidated]
        if mode == "pit" or (
            mode == "period_end" and utc_datetime(selected.available_at) <= utc_datetime(current.as_of)
        ):
            prior_candidates = [f for f in prior_candidates
                                if utc_datetime(f.available_at) <= utc_datetime(current.as_of)]
        elif mode == "period_end":
            prior_candidates = [f for f in prior_candidates
                                if utc_datetime(f.available_at) == utc_datetime(selected.available_at)]
        if not prior_candidates:
            return GrowthResult("rejected", "no_same_filing_adjacent_annual_predecessor", current)
        status, reason, previous = self._resolve(prior_candidates)
        evidence = tuple(sorted(prior_candidates, key=lambda f: f.fact_id))
        if status != "ok" or previous is None:
            return GrowthResult(status, f"previous:{reason}", current, evidence=evidence)
        if previous.basis_id != selected.basis_id or previous.unit != selected.unit:
            return GrowthResult("rejected", "incomparable_unit_or_accounting_basis", current, previous, evidence=evidence)
        current_concept = (selected.concept_namespace, selected.concept.rsplit(":", 1)[-1])
        previous_concept = (previous.concept_namespace, previous.concept.rsplit(":", 1)[-1])
        if current_concept != previous_concept:
            return GrowthResult("rejected", "unproven_cross_concept_comparability", current, previous, evidence=evidence)
        if utc_datetime(previous.available_at) != utc_datetime(selected.available_at):
            return GrowthResult("rejected", "inconsistent_same_filing_availability", current, previous, evidence=evidence)
        if previous.number is None or previous.number <= 0:
            return GrowthResult("rejected", "nonpositive_growth_denominator", current, previous, evidence=evidence)
        if selected.number is None:
            return GrowthResult("rejected", "missing_current_value", current, previous, evidence=evidence)
        with localcontext() as context:
            context.prec = 34
            growth = selected.number / previous.number - 1
        return GrowthResult("ok", "same_filing_same_concept_annual_pair", current, previous, decimal_text(growth), evidence)


# A concise alias for callers that name the component by its temporal behavior.
TemporalEngine = RevenueEngine
