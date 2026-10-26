"""Fixed-corpus experiments with explicit paired denominators and tie-aware ranks.

All three modes use identical company/fiscal-year/month-end keys and the engine's
same growth formula. Rates describe this purposive, repeatedly observed corpus;
they are not market frequencies, independent samples, or return estimates.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Iterable

from .engine import RevenueEngine
from .models import RevenueFact, decimal_text, iso_utc, load_facts, utc_datetime

MODES = ("period_end", "latest", "pit")
BASELINES = ("period_end", "latest")
SPLITS = frozenset(("development", "holdout"))
CORPUS_CUTOFF = "2025-12-31T23:59:59Z"
OBSERVATION_COLUMNS = (
    "split", "cik", "ticker", "fiscal_year", "period_end", "as_of", "mode",
    "revenue_status", "revenue_reason", "revenue_value", "revenue_identity",
    "accession", "available_at", "effective_at", "revenue_future_provenance",
    "growth_status", "growth_reason", "growth_value", "previous_identity",
    "previous_revenue_value", "growth_future_provenance",
)
RANKING_COLUMNS = (
    "split", "fiscal_year", "as_of", "baseline", "record_type", "status",
    "candidate_count", "baseline_usable_count", "pit_usable_count", "common_count",
    "cik", "ticker", "baseline_growth", "pit_growth", "baseline_rank", "pit_rank",
    "rank_shift", "rank_changed", "changed_members", "mean_absolute_rank_shift",
)


@dataclass(frozen=True)
class ExperimentResult:
    observations: list[dict[str, Any]]
    rankings: list[dict[str, Any]]
    summary: dict[str, Any]


def month_end_queries(start_year: int = 2019, end_year: int = 2025) -> tuple[str, ...]:
    """Last representable microsecond of every UTC calendar month, inclusively."""
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    return tuple(
        f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}T23:59:59.999999Z"
        for year in range(start_year, end_year + 1) for month in range(1, 13)
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _mean(values: list[Decimal]) -> str | None:
    if not values:
        return None
    with localcontext() as context:
        context.prec = 34
        return decimal_text(sum(values) / len(values))


def _distribution(values: list[Decimal]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "mean": None, "median": None, "max": None}
    with localcontext() as context:
        context.prec = 34
        middle = len(ordered) // 2
        median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {"count": len(ordered), "mean": _mean(ordered), "median": decimal_text(median), "max": decimal_text(ordered[-1])}


def average_ranks(values: dict[str, Decimal]) -> dict[str, Decimal]:
    """Highest value ranks first; exact Decimal ties get their mean ordinal rank."""
    # Unary minus applies Decimal's active arithmetic precision. Avoid it here:
    # two distinct 34-digit growth values must not become equal 28-digit keys.
    ranked = sorted(sorted(values), key=values.__getitem__, reverse=True)
    result: dict[str, Decimal] = {}
    left = 0
    while left < len(ranked):
        right = left + 1
        while right < len(ranked) and values[ranked[right]] == values[ranked[left]]:
            right += 1
        rank = (Decimal(left + 1) + Decimal(right)) / 2
        result.update({key: rank for key in ranked[left:right]})
        left = right
    return result


def _mode_summary(rows: list[dict], field: str) -> dict:
    statuses = Counter(row[f"{field}_status"] for row in rows)
    usable = [row for row in rows if row[f"{field}_status"] == "ok"]
    future = sum(row[f"{field}_future_provenance"] for row in usable)
    return {
        "total_queries": len(rows),
        "usable_count": len(usable),
        "coverage": _rate(len(usable), len(rows)),
        "status_counts": {name: statuses.get(name, 0) for name in ("ok", "missing", "ambiguous", "rejected")},
        "nonusable_reason_counts": dict(sorted(Counter(row[f"{field}_reason"] for row in rows if row[f"{field}_status"] != "ok").items())),
        "future_provenance_count": future,
        "future_provenance_denominator": len(usable),
        "future_provenance_rate": _rate(future, len(usable)),
    }


def _paired_summary(pairs: list[tuple[dict, dict]], field: str) -> dict:
    paired = [(baseline, pit) for baseline, pit in pairs if baseline[f"{field}_status"] == pit[f"{field}_status"] == "ok"]
    baseline_only = sum(b[f"{field}_status"] == "ok" and p[f"{field}_status"] != "ok" for b, p in pairs)
    pit_only = sum(b[f"{field}_status"] != "ok" and p[f"{field}_status"] == "ok" for b, p in pairs)
    neither = len(pairs) - len(paired) - baseline_only - pit_only
    deltas: list[Decimal] = []
    sign_changes = 0
    future_equal = 0
    with localcontext() as context:
        context.prec = 34
        for baseline, pit in paired:
            b, p = Decimal(baseline[f"{field}_value"]), Decimal(pit[f"{field}_value"])
            deltas.append(abs(b - p))
            sign_changes += (b > 0) - (b < 0) != (p > 0) - (p < 0)
            future_equal += baseline[f"{field}_future_provenance"] == 1 and b == p
    changed = sum(value != 0 for value in deltas)
    result = {
        "total_query_keys": len(pairs),
        "both_usable_count": len(paired),
        "baseline_only_usable_count": baseline_only,
        "pit_only_usable_count": pit_only,
        "neither_usable_count": neither,
        "numeric_changed_count": changed,
        "numeric_changed_denominator": len(paired),
        "numeric_changed_rate": _rate(changed, len(paired)),
        "absolute_difference": _distribution(deltas),
        "baseline_future_provenance_in_pairs": sum(b[f"{field}_future_provenance"] for b, _ in paired),
        "future_provenance_without_numeric_change_count": future_equal,
    }
    if field == "growth":
        result.update(direction_changed_count=sign_changes, direction_changed_denominator=len(paired),
                      direction_changed_rate=_rate(sign_changes, len(paired)))
    return result


def _rankings(keys: dict[tuple, dict[str, dict]], split: str) -> tuple[list[dict], dict]:
    groups: dict[tuple[int, str], list[dict[str, dict]]] = defaultdict(list)
    for (_, fiscal_year, _, as_of), modes in keys.items():
        groups[(fiscal_year, as_of)].append(modes)
    output: list[dict] = []
    summaries: dict[str, dict] = {}
    for baseline in BASELINES:
        evaluated = 0
        shifts: list[Decimal] = []
        changed_memberships = 0
        for (fiscal_year, as_of), items in sorted(groups.items()):
            b = {item[baseline]["cik"]: item[baseline] for item in items if item[baseline]["growth_status"] == "ok"}
            p = {item["pit"]["cik"]: item["pit"] for item in items if item["pit"]["growth_status"] == "ok"}
            common = sorted(set(b) & set(p))
            base = dict(split=split, fiscal_year=fiscal_year, as_of=as_of, baseline=baseline,
                        candidate_count=len(items), baseline_usable_count=len(b), pit_usable_count=len(p), common_count=len(common))
            if len(common) < 2:
                output.append({**base, "record_type": "group", "status": "insufficient_common_members"})
                continue
            evaluated += 1
            b_ranks = average_ranks({cik: Decimal(b[cik]["growth_value"]) for cik in common})
            p_ranks = average_ranks({cik: Decimal(p[cik]["growth_value"]) for cik in common})
            group_shifts = [abs(b_ranks[cik] - p_ranks[cik]) for cik in common]
            changed = sum(value != 0 for value in group_shifts)
            shifts.extend(group_shifts)
            changed_memberships += changed
            output.append({**base, "record_type": "group", "status": "evaluated",
                           "changed_members": changed, "mean_absolute_rank_shift": _mean(group_shifts)})
            for cik in common:
                shift = b_ranks[cik] - p_ranks[cik]
                output.append({**base, "record_type": "member", "status": "evaluated", "cik": cik,
                               "ticker": b[cik]["ticker"], "baseline_growth": b[cik]["growth_value"],
                               "pit_growth": p[cik]["growth_value"], "baseline_rank": decimal_text(b_ranks[cik]),
                               "pit_rank": decimal_text(p_ranks[cik]), "rank_shift": decimal_text(shift),
                               "rank_changed": int(shift != 0)})
        summaries[baseline] = {
            "candidate_groups": len(groups), "evaluated_groups": evaluated,
            "insufficient_common_groups": len(groups) - evaluated,
            "common_memberships": len(shifts), "changed_memberships": changed_memberships,
            "rank_change_denominator": len(shifts), "rank_change_rate": _rate(changed_memberships, len(shifts)),
            "mean_absolute_rank_shift": _mean(shifts),
        }
    return output, summaries


def evaluate(facts: Iterable[RevenueFact], targets: Iterable[dict], split: str,
             *, query_dates: Iterable[str] | None = None) -> ExperimentResult:
    """Evaluate one split without tuning, fetching, or modifying source records."""
    if split not in SPLITS:
        raise ValueError(f"split must be one of {sorted(SPLITS)}")
    facts = list(facts)
    normalized_targets = []
    seen = set()
    for target in targets:
        if target.get("split") != split:
            raise ValueError("Targets from different splits must not be pooled")
        row = dict(target)
        row["cik"] = str(row["cik"]).zfill(10)
        row["fiscal_year"] = int(row["fiscal_year"])
        row["period_end"] = date.fromisoformat(row["period_end"]).isoformat()
        if not 2019 <= row["fiscal_year"] <= 2024:
            raise ValueError("Target fiscal year must be in 2019–2024")
        key = (row["cik"], row["fiscal_year"])
        if key in seen:
            raise ValueError(f"Duplicate company/fiscal-year target: {key}")
        seen.add(key)
        normalized_targets.append(row)
    normalized_targets.sort(key=lambda row: (row["cik"], row["fiscal_year"], row["period_end"]))
    queries = tuple(sorted({iso_utc(value) for value in (query_dates if query_dates is not None else month_end_queries())}, key=utc_datetime))
    engine = RevenueEngine(facts, corpus_cutoff=CORPUS_CUTOFF)
    observations: list[dict] = []
    keyed: dict[tuple, dict[str, dict]] = {}
    for target in normalized_targets:
        for as_of in queries:
            if target["period_end"] > utc_datetime(as_of).date().isoformat():
                continue
            key = (target["cik"], target["fiscal_year"], target["period_end"], as_of)
            keyed[key] = {}
            for mode in MODES:
                growth = engine.query_growth(target["cik"], target["period_end"], as_of, mode=mode)
                revenue = growth.current
                fact = revenue.fact
                previous = growth.previous
                row = {
                    "split": split, "cik": target["cik"], "ticker": target["ticker"],
                    "fiscal_year": target["fiscal_year"], "period_end": target["period_end"], "as_of": as_of, "mode": mode,
                    "revenue_status": revenue.status, "revenue_reason": revenue.reason, "revenue_value": revenue.value,
                    "revenue_identity": fact.identity if fact else None, "accession": fact.accession if fact else None,
                    "available_at": fact.available_at if fact else None, "effective_at": revenue.effective_at,
                    "revenue_future_provenance": int(revenue.status == "ok" and revenue.uses_future_information),
                    "growth_status": growth.status, "growth_reason": growth.reason, "growth_value": growth.growth,
                    "previous_identity": previous.identity if previous else None,
                    "previous_revenue_value": previous.value if previous else None,
                    "growth_future_provenance": int(growth.status == "ok" and growth.uses_future_information),
                }
                observations.append(row)
                keyed[key][mode] = row
    rankings, rank_summary = _rankings(keyed, split)
    mode_summary = {
        mode: {field: _mode_summary([row for row in observations if row["mode"] == mode], field)
               for field in ("revenue", "growth")}
        for mode in MODES
    }
    comparisons = {
        baseline: {field: _paired_summary([(modes[baseline], modes["pit"]) for modes in keyed.values()], field)
                   for field in ("revenue", "growth")}
        for baseline in BASELINES
    }
    summary = {
        "schema_version": "filingtime-experiment-v1", "split": split,
        "corpus_cutoff": CORPUS_CUTOFF,
        "query_count": len(queries), "query_first": queries[0] if queries else None,
        "query_last": queries[-1] if queries else None,
        "target_count": len(normalized_targets), "company_count": len({t["cik"] for t in normalized_targets}),
        "query_key_count": len(keyed), "observation_count": len(observations),
        "source_fact_count": len(facts), "within_cutoff_fact_count": len(engine.facts),
        "modes": mode_summary, "comparisons_to_pit": comparisons, "rankings": rank_summary,
        "definitions": {
            "observation": "One target company/fiscal-year and month-end query, repeated once per mode; only completed financial periods are included.",
            "future_provenance": "Selected source version available_at is later than as_of; this is distinct from whether its numeric value differs.",
            "growth": "current / previous - 1, using the same filing, adjacent annual periods, equal unit and accounting basis, and positive denominator.",
            "comparison_denominator": "Both modes usable on the identical key. Baseline-only, PIT-only, and neither-usable keys are retained separately.",
            "rank": "Within fiscal year and as_of, each baseline is ranked against PIT on their common usable-growth company set, n>=2. Higher growth ranks first; exact ties use average ranks.",
            "rank_membership": "A company occurrence in one evaluated fiscal-year/query/baseline group, not an independent company observation.",
            "numeric_precision": "Financial values and differences are Decimal strings; rates of counts are descriptive floating-point ratios.",
        },
        "limitations": [
            "Purposive engineering corpus; no market-frequency or portfolio-return inference.",
            "Repeated monthly observations are dependent; no statistical significance is claimed.",
            "Different fiscal-year calendars can be grouped by the same year label; rankings are a mechanical sensitivity diagnostic, not economically synchronized investment signals.",
            "The latest selected statement may omit the adjacent prior fiscal year; strict same-filing growth is then refused rather than spliced from an older basis.",
            "A new source version can be future-dated while repeating the same number; future provenance and numeric distortion are reported separately.",
            "Human accounting review remains pending; no independent human agreement rate is reported.",
        ],
    }
    return ExperimentResult(observations, rankings, summary)


def _write_csv(path: Path, columns: tuple[str, ...], rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_experiment(root: str | Path, split: str) -> dict:
    """Read frozen normalized inputs and write deterministic result artifacts."""
    if split not in SPLITS:
        raise ValueError(f"split must be one of {sorted(SPLITS)}")
    root = Path(root)
    if split == "holdout":
        from .freeze import check_freeze
        if check_freeze(root)["status"] != "unchanged":
            raise ValueError("Holdout experiments require unchanged frozen rules")
    facts_path = root / "data/processed" / f"{split}_facts.jsonl"
    targets_path = root / "data/processed" / f"{split}_targets.json"
    result = evaluate(load_facts(facts_path), json.loads(targets_path.read_text(encoding="utf-8")), split)
    summary = result.summary
    summary["input_files"] = [
        {"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (facts_path, targets_path)
    ]
    out = root / "data/results"
    out.mkdir(parents=True, exist_ok=True)
    observations_path, rankings_path = out / f"{split}_observations.csv", out / f"{split}_rankings.csv"
    _write_csv(observations_path, OBSERVATION_COLUMNS, result.observations)
    _write_csv(rankings_path, RANKING_COLUMNS, result.rankings)
    summary["output_files"] = [
        {"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (observations_path, rankings_path)
    ]
    (out / f"{split}_summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return summary
