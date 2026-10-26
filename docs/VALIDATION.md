# Validation protocol

This document describes what the project checks and what the evidence can support. A passing test run is not a financial audit. Independent human review is **pending** unless a dated reviewer record explicitly says otherwise. An AI review, a second implementation, and an automated cross-check must keep their own labels.

## Claim and boundaries

FilingTime reconstructs annual consolidated revenue available within a specified set of SEC 10-K and 10-K/A filings under a fixed availability convention. It does not reconstruct every public disclosure, establish when investors first learned the figure, prove the issuer's economic facts, or demonstrate investment returns.

The corpus targets 12 nonfinancial US-GAAP issuers, fiscal years 2019–2024, with comparison periods where needed, and filings accepted no later than 2025-12-31. Eight issuers are development cases; four are a held-out evaluation set. Their identities, selection rationale, split, cutoff, parser version, mapping rules, and code revision must be recorded before evaluation. A targeted stress case is not a random sample and cannot establish a market-wide error rate.

## Clocks and immutable inputs

Keep the economic period, SEC acceptance timestamp, research availability timestamp, and retrieval timestamp separate. Convert timezone-aware timestamps to UTC; reject naive timestamps rather than silently assuming a zone. The availability convention is acceptance plus 24 elapsed hours. This is a reproducible research assumption, not an observed dissemination or trading time.

The SEC describes a delay between acceptance and web availability; it also distinguishes live API processing delays. Neither a filing date without a time nor the current API retrieval time is a substitute for historical public availability. See the [SEC timestamp and dissemination FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions) and [API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

For every input preserve its URL, accession number, retrieval time, relative file path, byte count, and SHA-256. Do not replace a prior byte-identical experiment input with a later download. The hash proves identity of bytes, not truth of their content. Missing raw inputs or unavailable historical metadata must be visible in the source manifest and coverage results.

## Independent evidence layers

| Layer | Evidence | Supports | Does not establish |
|---|---|---|---|
| Source | Original filing, context, table and explanatory note | What was reported in that document | Economic truth or first market disclosure |
| Semantic | Independently recorded reference labels and review decisions | Correct period, entity scope, unit and revision interpretation | All-company generalization |
| Parser | Arelle output and SEC extraction cross-check | Numeric/context discrepancies | Economic comparability by themselves |
| Temporal | Boundary tests and future-append tests | Defined time-selection rules | Completeness of public information |
| Robustness | Synthetic fault injection | Detection of the specified faults | Real-world precision or prevalence |
| Reproduction | Frozen inputs, locked environment and CI | Repeatability of this computation | Correctness of its assumptions |

XBRL International expressly distinguishes rule validation from factual accuracy. Its [validation overview](https://www.xbrl.org/the-standard/what/key-concepts-in-xbrl/validation/) is the basis for this separation. Companyfacts is a derived standard-taxonomy/entity-level extraction; Frames selects recently filed facts. Neither is the complete historical reference truth ([SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)).

## Reference annotation and held-out discipline

Use [ANNOTATION_GUIDE.md](ANNOTATION_GUIDE.md) to record decisions against original files. Record each annotator's role and whether they inspected system output before labeling. Labels made by the implementation agent are development annotations, not independent human labels. Unresolved labels remain unresolved; never relabel them merely to agree with the program.

1. Freeze the sample and rules before inspecting held-out values.
2. Record the frozen code/configuration hash and first held-out evaluation time.
3. Evaluate the held-out cases once under the frozen rules; retain failures.
4. If evaluation findings motivate changes, retain the first evaluation. Identify subsequent runs as post-evaluation revisions, not untouched holdout performance.
5. Report raw-source missingness separately from unsupported semantics and extraction failures.

An identical number in two contexts is not sufficient evidence that both denote consolidated annual revenue. Conversely, a different concept name does not by itself establish a change in economic meaning. Do not infer that every 10-K/A changes financial statements, or that a normal later 10-K cannot revise comparative periods.

## Three-mode experiment

All modes use the same corpus cutoff, query grid, candidate universe, unit policy, and revenue/growth definition. Only information timing/version selection changes.

| Mode | Intended behavior | Deliberate defect |
|---|---|---|
| `period_end` | Makes the first disclosed value available at its economic period end | Uses information before filing |
| `latest` | Uses the final cutoff-bounded version from the first disclosure's availability time | Backfills future revisions |
| `pit` | Uses the most recent eligible disclosure at the query time | None intended; failures must still be measured |

The first two are explicit contaminated baselines. The `latest` mode must not make a company-period appear before its original availability date; otherwise it combines the two defects. No baseline may use a filing beyond the corpus cutoff. A future version can be temporally ineligible even if its number happens to be identical; numeric difference and provenance leakage are distinct outcomes.

Growth needs two compatible annual periods from the same filing. Unit, entity scope and accounting basis must agree; the previous period must be the immediately preceding comparable fiscal year. A same-filing comparative pair does not eliminate the need to inspect restatement, discontinued-operation and policy notes. Do not splice unrelated periods or use a later prior-year number merely to complete a denominator. Zero prior revenue yields an undefined growth result and an explicit reason.

## Metrics and denominators

Publish integer numerators and denominators alongside percentages, for both development and held-out samples. A zero denominator is `not applicable`, never 0% success or 100% accuracy.

| Metric | Numerator | Denominator |
|---|---|---|
| Source coverage | Company-periods with required original evidence | All planned company-periods |
| Answer coverage | Queries with an accepted numeric answer | All scheduled queries |
| Refusal rate | Queries explicitly refused due to ambiguity/unsupported input | All scheduled queries |
| Numerical agreement | Accepted, resolvable reference cases whose value agrees within the predefined reporting-precision rule | Accepted cases with resolvable reference labels |
| Semantic agreement | Correct unit, period, scope and version, as well as value | Cases with resolvable semantic reference labels |
| Leakage precision | Correctly identified temporally invalid selections | All selections flagged as temporally invalid |
| Leakage recall | Correctly identified temporally invalid selections | All independently labeled temporally invalid selections |
| Growth change | Comparable paired queries with changed growth (and separately changed sign) | Queries with valid comparable growth in both modes |
| Rank change | Issuers with a changed rank at a fixed query date | The common evaluable issuer set at that date |

Without independently adjudicated temporal labels, do not report measured real-world precision/recall; report synthetic detection results separately. Ranks use a fixed tie convention and only the common evaluable set. Publish excluded counts and reasons by mode. Different coverage must not silently change the ranking universe. Small engineering samples support case-based findings, not population prevalence estimates.

The executable [synthetic injection benchmark](../scripts/benchmark_injections.py) stores literal expected labels before calling the engine. Its [generated result](../data/results/synthetic_injection_benchmark.json) reports scenario-level TP/FP/TN/FN, scoring coverage, separate refusals, and a separate semantic-fault classification table. Test assertion counts are not detection-rate denominators. An unexpected refusal of a labelled case reduces coverage and is never counted as a true negative. The checked-in run has three positive and four negative scored temporal cases, plus two separately reported refusals and eight semantic cases. These artificial cases are not real human-labelled ground truth.

## Mandatory adversarial checks

These checks use synthetic fixtures unless a source-linked real case is explicitly identified.

| Scenario | Expected result |
|---|---|
| Query one instant before a record becomes available | `pit` does not return that record |
| Query exactly at its availability instant | It may be selected, subject to semantic checks |
| Append arbitrarily changed future records | Earlier `pit` answers and their selected provenance remain unchanged |
| Permute or duplicate equivalent inputs | Values and selected evidence remain deterministic |
| Later normal 10-K revises an old comparative figure | The old snapshot remains intact; later eligible snapshot may change |
| 10-K/A contains no revenue change | No synthetic revenue revision is manufactured |
| Two conflicting facts in the same eligible disclosure | Refuse ambiguity rather than use arbitrary row order |
| Mix currency units or consolidated and segment contexts | Reject incompatibility or exclude documented out-of-scope contexts |
| Short-period or quarterly value resembles an annual total | Do not accept it as annual merely because the end date matches |
| Change the prior fiscal period, basis or denominator to zero | Refuse or report undefined growth with a specific reason |
| Supply a filing accepted after the cutoff | It cannot enter any experimental mode |
| Corrupt a raw byte or an identity field | The integrity check fails; semantic testing must not erase this failure |

## Release evidence and honest status

The release should point to actual manifests, fixed inputs, test output, held-out evaluation receipt and generated experiment tables. This protocol is not itself evidence that any gate has passed. For each gate record `passed`, `failed`, `pending`, or `not applicable`, with a path/URL to the supporting result.

At least one complete demonstration should link a historical query to the selected source document, field/context, version choice and growth consequence. A real failure case must be genuine and source-backed. If the search found none, report the search scope and zero discoveries; do not convert an injected case into an empirical finding.

Public descriptions and résumé statements may use only completed work and measured results. Claims of independent human validation remain unavailable until an actual independent human review has occurred.
