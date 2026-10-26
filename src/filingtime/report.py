"""Generate the research report from saved results, without hand-entered metrics."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .audit import coverage_report, read_jsonl, verify_corpus, verify_support_files
from .engine import RevenueEngine
from .freeze import check_freeze
from .models import load_facts

LABELS = {"period_end": "Period-end baseline", "latest": "Latest-value baseline", "pit": "Point in time"}
MODES = ("period_end", "latest", "pit")


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{100 * value:.2f}%"


def version_changes(root: Path) -> list[dict]:
    if check_freeze(root)["status"] != "unchanged":
        raise ValueError("Held-out report inputs require unchanged frozen rules")
    changes = []
    for split in ("development", "holdout"):
        facts = load_facts(root / f"data/processed/{split}_facts.jsonl")
        targets = json.loads((root / f"data/processed/{split}_targets.json").read_text(encoding="utf-8"))
        lookup = {(t["cik"], t["period_end"]): t for t in targets}
        engine = RevenueEngine(facts)
        groups = defaultdict(set)
        for fact in facts:
            if (fact.cik, fact.period_end) in lookup:
                groups[(fact.cik, fact.period_end)].add(fact.available_at)
        for key, dates in sorted(groups.items()):
            previous = None
            for instant in sorted(dates):
                result = engine.query_revenue(*key, instant)
                if result.status != "ok":
                    previous = None
                    continue
                current = result.fact
                if previous is not None and previous.number != current.number:
                    target = lookup[key]
                    changes.append({
                        "split": split, "cik": key[0], "ticker": target["ticker"],
                        "fiscal_year": target["fiscal_year"], "period_end": key[1],
                        "old_value": previous.value, "new_value": current.value, "unit": current.unit,
                        "old_available_at": previous.available_at, "new_available_at": current.available_at,
                        "old_accession": previous.accession, "new_accession": current.accession,
                        "old_source": previous.source_url, "new_source": current.source_url,
                        "old_anchor": previous.evidence_anchor, "new_anchor": current.evidence_anchor,
                        "absolute_change": str(abs(current.number - previous.number)),
                        "interpretation": "Source-version change; accounting cause requires separate source review",
                    })
                previous = current
    return changes


def _figure(summaries: dict, destination: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "filingtime-v1"})
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    colors = ["#d49b34", "#bc574c", "#267a91"]
    short = ["Period end", "Latest", "PIT"]
    for row, split in enumerate(("development", "holdout")):
        data = summaries[split]
        for col, (field, metric, title) in enumerate((
            ("revenue", "future_provenance_rate", "Future source versions / usable revenue queries"),
            ("growth", "coverage", "Usable growth queries / all identified-target queries"),
        )):
            ax = axes[row, col]
            values = [data["modes"][mode][field][metric] for mode in MODES]
            bars = ax.bar(short, [100 * (value or 0) for value in values], color=colors, width=0.62)
            ax.set_ylim(0, 112)
            ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
            ax.set_axisbelow(True)
            ax.grid(axis="y", color="#e5e9ec")
            ax.set_title(f"{split.title()} · {title}", loc="left", fontsize=10, pad=12)
            for bar, value in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                        "N/A" if value is None else f"{value * 100:.1f}%", ha="center", fontsize=10)
    fig.suptitle("FilingTime | Source timing and strict comparability", fontsize=17, fontweight="bold")
    fig.supxlabel("Descriptive challenge corpus. Repeated months are dependent; these are not market-frequency or return estimates.", fontsize=9)
    destination.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination / "research_summary.png", dpi=180, metadata={"Software": "FilingTime"})
    fig.savefig(destination / "research_summary.svg", metadata={"Date": None, "Creator": "FilingTime"})
    plt.close(fig)


def build_report(root: str | Path) -> dict:
    root = Path(root).resolve()
    if check_freeze(root)["status"] != "unchanged":
        raise ValueError("Held-out reporting requires unchanged frozen rules")
    summaries = {split: json.loads((root / f"data/results/{split}_summary.json").read_text(encoding="utf-8"))
                 for split in ("development", "holdout")}
    for summary in summaries.values():
        for record in summary["input_files"] + summary["output_files"]:
            path = (root / record["path"]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("Experiment summary references an unavailable input or output")
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError(f"Stale experiment summary: {record['path']}")
    coverage = coverage_report(root)
    corpus, support = verify_corpus(root), verify_support_files(root)
    freeze = check_freeze(root)
    crosschecks = {}
    for split in ("development", "holdout"):
        check = json.loads((root / f"data/results/{split}_companyfacts_crosscheck.json").read_text(encoding="utf-8"))["summary"]
        if hashlib.sha256((root / f"data/processed/{split}_facts.jsonl").read_bytes()).hexdigest() != check["input_facts_sha256"]:
            raise ValueError("Companyfacts cross-check refers to stale normalized facts")
        crosschecks[split] = check
    injections = json.loads((root / "data/results/synthetic_injection_benchmark.json").read_text(encoding="utf-8"))
    changes = version_changes(root)
    output = root / "data/results"
    (output / "source_coverage.json").write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8", newline="\n")
    columns = ("split", "cik", "ticker", "fiscal_year", "period_end", "old_value", "new_value", "unit",
               "old_available_at", "new_available_at", "old_accession", "new_accession", "old_source",
               "new_source", "old_anchor", "new_anchor", "absolute_change", "interpretation")
    with (output / "source_version_changes.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(changes)
    _figure(summaries, root / "docs/assets")
    rows = [
        "# FilingTime research report", "",
        "This report is generated from the committed experiment summaries. It evaluates source timing and revenue-feature construction, not investment performance.", "",
        "## Research question", "",
        "At a historical query time, which annual consolidated revenue version was allowed within the specified SEC annual-filing collection? How do premature use and later-version backfilling change the resulting feature?", "",
        "The source window contains 10-K and 10-K/A filings accepted through 2025-12-31T23:59:59Z. The research availability convention is SEC acceptance plus 24 elapsed hours. Earlier 8-Ks and earnings announcements are outside scope. This is not a claim of first public knowledge.", "",
        "## Evidence and sample coverage", "",
        f"Archived original files: **{corpus['source_files']}**; annual/amended filings: **{corpus['filing_count']}**; offline taxonomy files: **{support['taxonomy_files']}**. Source hash verification: **{corpus['status']}**. Frozen-rule comparison: **{freeze['status']}**.", "",
        "| Split | Planned companies | Planned company-years | Identified target years | Missing target years | Collected / parsed filings |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split, record in coverage.items():
        rows.append(f"| {split} | {record['planned_companies']} | {record['planned_company_years']} | {record['identified_target_company_years']} | {len(record['missing_company_years'])} | {record['collected_filings']} / {record['parsed_filings']} |")
    rows += ["", "Company-year identification is not accepted-fact accuracy. Any missing company-year remains visible in [source_coverage.json](../data/results/source_coverage.json). Query metrics below describe identified targets; they must not hide this upstream coverage denominator.", "",
             "## Separate extraction cross-check", "",
             "The SEC Companyfacts snapshot is used only for a separate extraction comparison. Matching requires the same issuer, accession, concept namespace/local name, period and unit. It does not supply query values and is not a historical API snapshot or independent economic ground truth.", "",
             "| Split | Unique admitted source facts | Exact matches | Numeric mismatches | Not comparable / outside API coverage |",
             "|---|---:|---:|---:|---:|"]
    for split, check in crosschecks.items():
        rows.append(f"| {split} | {check['unique_accepted_facts']} | {check['exact_match_count']} | {check['status_counts'].get('numeric_mismatch', 0)} | {check['unique_accepted_facts'] - check['comparable_count']} |")
    rows += ["", "## Controlled comparison", "",
             "All modes use the same company-period-query keys and growth formula. Period-end mode brings only the first disclosure back to the economic period end; later revisions keep their actual availability. Latest mode backfills the final collected version from the first original availability date. PIT selects only eligible versions.", "",
             "![Timing and comparability diagnostics](assets/research_summary.png)", "",
             "| Split | Mode | Usable revenue / queries | Future-source revenue / usable | Usable growth / queries |",
             "|---|---|---:|---:|---:|"]
    for split, summary in summaries.items():
        for mode in MODES:
            rev, growth = summary["modes"][mode]["revenue"], summary["modes"][mode]["growth"]
            rows.append(f"| {split} | {LABELS[mode]} | {rev['usable_count']} / {rev['total_queries']} | {rev['future_provenance_count']} / {rev['future_provenance_denominator']} | {growth['usable_count']} / {growth['total_queries']} |")
    rows += ["", "A later source can repeat the same number. Future provenance is therefore measured separately from numeric change. PIT is required to have zero future-source use; this invariant alone does not establish semantic accounting accuracy.", "",
             "## Differences on common usable observations", "",
             "| Split | Baseline | Changed revenue / paired usable | Changed growth / paired usable | Growth direction flips / paired usable | Changed ranks / common memberships |",
             "|---|---|---:|---:|---:|---:|"]
    for split, summary in summaries.items():
        for baseline in ("period_end", "latest"):
            rev = summary["comparisons_to_pit"][baseline]["revenue"]
            growth = summary["comparisons_to_pit"][baseline]["growth"]
            rank = summary["rankings"][baseline]
            rows.append(f"| {split} | {LABELS[baseline]} | {rev['numeric_changed_count']} / {rev['numeric_changed_denominator']} | {growth['numeric_changed_count']} / {growth['numeric_changed_denominator']} | {growth['direction_changed_count']} / {growth['direction_changed_denominator']} | {rank['changed_memberships']} / {rank['common_memberships']} |")
    rows += ["", "The period-end intervention changes only the first availability timestamp. Once both it and PIT are usable, their values should match. Its error is visible in premature source use and baseline-only usable observations, not a nonzero paired numeric difference. The pre-evaluation [protocol clarification](PROTOCOL_AMENDMENT_01.md) and superseded exploration remain available.", "",
             "A rank membership is one company in one fiscal-year/query comparison, not an independent observation. Ranks use only the common usable set (at least two companies), with average ranks for exact ties. Fiscal calendars differ, so this is a mechanical sensitivity diagnostic rather than a synchronized stock-selection strategy.", "",
             "## Source-version changes", "",
             f"The collection contains **{len(changes)}** transitions with changed admitted revenue values for target fiscal years. The complete transition ledger is [source_version_changes.csv](../data/results/source_version_changes.csv). These are source-version changes, not automatically accounting restatements or vendor errors.", "",
             "| Split | Company / FY | Earlier value (USD) | Later value (USD) | Source pair |", "|---|---|---:|---:|---|"]
    for row in sorted(changes, key=lambda r: Decimal(r["absolute_change"]), reverse=True)[:8]:
        earlier = row["old_source"] + (row["old_anchor"] if row["old_anchor"].startswith("#") else "")
        later = row["new_source"] + (row["new_anchor"] if row["new_anchor"].startswith("#") else "")
        rows.append(f"| {row['split']} | {row['ticker']} / {row['fiscal_year']} | {Decimal(row['old_value']):,.0f} | {Decimal(row['new_value']):,.0f} | [earlier]({earlier}) · [later]({later}) |")
    if not changes:
        rows.append("| — | No admitted numeric version change found | — | — | This does not imply no timing leakage |")
    checks = read_jsonl(root / "data/reference/source_checks.jsonl")
    matrix = injections["temporal_summary"]["confusion_matrix"]
    temporal = injections["temporal_summary"]
    semantic = injections["semantic_summary"]
    rows += ["", "The displayed examples are selected by absolute dollar change, not randomly. Interpretation requires the original accounting-policy, reclassification, disposal and restatement notes. See [source cases](SOURCE_CASES.md) for independently inspected document examples.", "",
             "## Verification and limitations", "",
             f"The repository contains **{len(checks)}** independently performed AI source checks. They are explicitly labeled as AI work; **independent human review remains pending**. The [review template](SOURCE_REVIEW_TEMPLATE.md) supports a reviewer who did not develop the code. No human accuracy percentage or audit opinion is claimed.", "",
             f"The labeled **synthetic** temporal benchmark records TP={matrix['TP']}, FP={matrix['FP']}, TN={matrix['TN']}, FN={matrix['FN']} over {temporal['scoring_coverage']['numerator']} scored cases; {temporal['observed_refusal_count']} refusals are separate. Another {semantic['expectation_match_count']} / {semantic['scenario_count']} designed semantic scenarios matched their prescribed outcomes. These are checks on named injected faults, not real-world precision/recall estimates. Full inputs and labels are in [the synthetic benchmark](../data/results/synthetic_injection_benchmark.json).", "",
             "- Arelle supplies general XBRL validation plus the fixed SEC inline transformation module; this is not full EDGAR Filer Manual certification.",
             "- Primary-statement mapping uses explicit concept, dimension, unit and same-role calculation evidence. Unsupported semantics are refused; coverage and refusal reasons remain in the results.",
             "- Growth requires a matching adjacent annual pair in one filing and statement basis, with equal concept namespace/local name and currency. This is a structural comparability check, not certification of unchanged accounting policy. A later filing can update a target year without including its predecessor; such growth queries are refused, not filled from an older basis.",
             "- The twelve issuers form a purposive engineering corpus. Neither observed failure shares nor repeated monthly comparisons estimate a market-wide frequency or a statistically independent sample.",
             "- Revenue updates can be legitimate consequences of business-boundary or accounting-policy changes. Feature differences do not demonstrate excess returns, causal effects, or trading viability.",
             "- Hashes establish byte identity, tests establish specific code properties, and reproductions establish computational consistency. None alone proves accounting truth.", "",
             "## Reproduction", "", "```console", "uv sync --frozen", "uv run filingtime verify", "uv run filingtime demo", "uv run python scripts/reproduce.py --work-dir ./work/reproduction", "```", "",
             "For the full original-filing replay, add `--reparse`. See [validation](VALIDATION.md), [protocol](PROTOCOL.md), and [third-party notices](THIRD_PARTY_NOTICES.md). The raw taxonomy bytes and their notices retain their original terms.", ""]
    report = root / "docs/REPORT.md"
    report.write_text("\n".join(rows), encoding="utf-8", newline="\n")
    return {"report": "docs/REPORT.md", "figure": "docs/assets/research_summary.png",
            "version_change_transitions": len(changes), "source_checks": len(checks),
            "human_review_status": "pending", "freeze_status": freeze["status"]}
