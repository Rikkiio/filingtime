# FilingTime research report

This report is generated from the committed experiment summaries. It evaluates source timing and revenue-feature construction, not investment performance.

## Evaluation status: original failure, then repaired replay

**The first frozen evaluation failed closed before normalization outputs were written.** Foot Locker's fiscal-year label conflicted across two filings. The [original failure receipt](../data/manifests/holdout_first_evaluation.json) remains the result of that first attempt.

Published results for the four originally reserved issuers have status **post_evaluation_metadata_repaired_replay**, with **1** documented metadata correction(s). They are **not untouched holdout results**. The report verifies the [recovery receipt](../data/manifests/holdout_recovery.json) against its current input and derived-output hashes before rendering these numbers. See the [source evidence and repair procedure](POST_EVALUATION_REPAIR.md).

Original filing bytes, parsed audits and frozen computational rules are preserved. An unchanged rule hash proves byte identity; it does not undo the post-evaluation inspection and annotation. The source-supported fiscal-year correction changes target metadata, not financial amounts, but can affect target membership and ranking groups. Artifact filenames retain the split name `holdout`; tables and figures label it as former holdout, repaired.

## Research question

At a historical query time, which annual consolidated revenue version was allowed within the specified SEC annual-filing collection? How do premature use and later-version backfilling change the resulting feature?

The source window contains 10-K and 10-K/A filings accepted through 2025-12-31T23:59:59Z. The research availability convention is SEC acceptance plus 24 elapsed hours. Earlier 8-Ks and earnings announcements are outside scope. This is not a claim of first public knowledge.

## Evidence and sample coverage

Archived original files: **800**; annual/amended filings: **87**; offline taxonomy files: **174**. Source hash verification: **passed**. Frozen-rule comparison: **unchanged**.

| Split | Planned companies | Planned company-years | Identified target years | Missing target years | Collected / parsed filings |
|---|---:|---:|---:|---:|---:|
| Development | 8 | 48 | 48 | 0 | 57 / 57 |
| Former holdout (repaired) | 4 | 24 | 24 | 0 | 30 / 30 |

Company-year identification is not accepted-fact accuracy. Any missing company-year remains visible in [source_coverage.json](../data/results/source_coverage.json). Query metrics below describe identified targets; they must not hide this upstream coverage denominator.

## Separate extraction cross-check

The SEC Companyfacts snapshot is used only for a separate extraction comparison. Matching requires the same issuer, accession, concept namespace/local name, period and unit. It does not supply query values and is not a historical API snapshot or independent economic ground truth.

| Split | Unique admitted source facts | Exact matches | Numeric mismatches | Not comparable / outside API coverage |
|---|---:|---:|---:|---:|
| Development | 171 | 171 | 0 | 0 |
| Former holdout (repaired) | 87 | 87 | 0 | 0 |

## Controlled comparison

All modes use the same company-period-query keys and growth formula. Period-end mode brings only the first disclosure back to the economic period end; later revisions keep their actual availability. Latest mode backfills the final collected version from the first original availability date. PIT selects only eligible versions.

![Timing and comparability diagnostics](assets/research_summary.png)

| Split | Mode | Usable revenue / queries | Future-source revenue / usable | Usable growth / queries |
|---|---|---:|---:|---:|
| Development | Period-end baseline | 2158 / 2158 | 89 / 2158 | 1149 / 2158 |
| Development | Latest-value baseline | 2069 / 2158 | 940 / 2069 | 218 / 2158 |
| Development | Point in time | 2069 / 2158 | 0 / 2069 | 1060 / 2158 |
| Former holdout (repaired) | Period-end baseline | 1066 / 1066 | 40 / 1066 | 569 / 1066 |
| Former holdout (repaired) | Latest-value baseline | 1026 / 1066 | 513 / 1026 | 73 / 1066 |
| Former holdout (repaired) | Point in time | 1026 / 1066 | 0 / 1026 | 529 / 1066 |

A later source can repeat the same number. Future provenance is therefore measured separately from numeric change. PIT is required to have zero future-source use; this invariant alone does not establish semantic accounting accuracy.

## Missing inputs and explicit refusals

Refused means an ambiguous or rejected result. Missing is reported separately and can include a disclosure that is not yet available. None of these outcomes is a zero financial value. Every fraction below uses all scheduled queries for that split, mode and feature, including nonusable outcomes.

| Split | Mode | Feature | Missing / all queries | Refused / all queries | Refusal detail: ambiguous; rejected |
|---|---|---|---:|---:|---:|
| Development | Period-end baseline | revenue | 0 / 2158 | 0 / 2158 | 0; 0 |
| Development | Period-end baseline | growth | 0 / 2158 | 1009 / 2158 | 0; 1009 |
| Development | Latest-value baseline | revenue | 89 / 2158 | 0 / 2158 | 0; 0 |
| Development | Latest-value baseline | growth | 89 / 2158 | 1851 / 2158 | 0; 1851 |
| Development | Point in time | revenue | 89 / 2158 | 0 / 2158 | 0; 0 |
| Development | Point in time | growth | 89 / 2158 | 1009 / 2158 | 0; 1009 |
| Former holdout (repaired) | Period-end baseline | revenue | 0 / 1066 | 0 / 1066 | 0; 0 |
| Former holdout (repaired) | Period-end baseline | growth | 0 / 1066 | 497 / 1066 | 0; 497 |
| Former holdout (repaired) | Latest-value baseline | revenue | 40 / 1066 | 0 / 1066 | 0; 0 |
| Former holdout (repaired) | Latest-value baseline | growth | 40 / 1066 | 953 / 1066 | 0; 953 |
| Former holdout (repaired) | Point in time | revenue | 40 / 1066 | 0 / 1066 | 0; 0 |
| Former holdout (repaired) | Point in time | growth | 40 / 1066 | 497 / 1066 | 0; 497 |

Detailed reasons remain in the [development summary](../data/results/development_summary.json) and [metadata-repaired replay summary](../data/results/holdout_summary.json). A refusal is a coverage outcome, not evidence that the issuer's filing is erroneous.

## Availability outside the common usable set

Each row partitions the same scheduled query keys into four mutually exclusive groups. Baseline-only results remain visible here rather than disappearing from the paired numeric and rank comparisons.

| Split | Baseline | Feature | Both usable | Baseline only | PIT only | Neither usable | All query keys |
|---|---|---|---:|---:|---:|---:|---:|
| Development | Period-end baseline | revenue | 2069 | 89 | 0 | 0 | 2158 |
| Development | Period-end baseline | growth | 1060 | 89 | 0 | 1009 | 2158 |
| Development | Latest-value baseline | revenue | 2069 | 0 | 0 | 89 | 2158 |
| Development | Latest-value baseline | growth | 218 | 0 | 842 | 1098 | 2158 |
| Former holdout (repaired) | Period-end baseline | revenue | 1026 | 40 | 0 | 0 | 1066 |
| Former holdout (repaired) | Period-end baseline | growth | 529 | 40 | 0 | 497 | 1066 |
| Former holdout (repaired) | Latest-value baseline | revenue | 1026 | 0 | 0 | 40 | 1066 |
| Former holdout (repaired) | Latest-value baseline | growth | 73 | 0 | 456 | 537 | 1066 |

## Differences on common usable observations

| Split | Baseline | Changed revenue / paired usable | Changed growth / paired usable | Growth direction flips / paired usable | Changed ranks / common memberships |
|---|---|---:|---:|---:|---:|
| Development | Period-end baseline | 0 / 2069 | 0 / 1060 | 0 / 1060 | 0 / 1055 |
| Development | Latest-value baseline | 130 / 2069 | 23 / 218 | 0 / 218 | 0 / 218 |
| Former holdout (repaired) | Period-end baseline | 0 / 1026 | 0 / 529 | 0 / 529 | 0 / 504 |
| Former holdout (repaired) | Latest-value baseline | 99 / 1026 | 0 / 73 | 0 / 73 | 0 / 49 |

The period-end intervention changes only the first availability timestamp. Once both it and PIT are usable, their values should match. Its error is visible in premature source use and baseline-only usable observations, not a nonzero paired numeric difference. The pre-evaluation [protocol clarification](PROTOCOL_AMENDMENT_01.md) and superseded exploration remain available.

A rank membership is one company in one fiscal-year/query comparison, not an independent observation. Ranks use only the common usable set (at least two companies), with average ranks for exact ties. They do not measure how premature availability changes the composition of the available universe. Fiscal calendars differ, so this is a mechanical sensitivity diagnostic rather than a synchronized stock-selection strategy.

## Source-version changes

The collection contains **13** transitions with changed admitted revenue values for target fiscal years. The complete transition ledger is [source_version_changes.csv](../data/results/source_version_changes.csv). These are source-version changes, not automatically accounting restatements or vendor errors.

| Split | Company / FY | Earlier value (USD) | Later value (USD) | Source pair |
|---|---|---:|---:|---|
| Development | GE / 2023 | 67,954,000,000 | 35,348,000,000 | [earlier](https://www.sec.gov/Archives/edgar/data/40545/000004054524000027/ge-20231231.htm#f-3104) · [later](https://www.sec.gov/Archives/edgar/data/40545/000004054525000015/ge-20241231.htm#f-2949) |
| Development | GE / 2022 | 58,100,000,000 | 29,139,000,000 | [earlier](https://www.sec.gov/Archives/edgar/data/40545/000004054524000027/ge-20231231.htm#f-3108) · [later](https://www.sec.gov/Archives/edgar/data/40545/000004054525000015/ge-20241231.htm#f-2950) |
| Development | GE / 2022 | 76,555,000,000 | 58,100,000,000 | [earlier](https://www.sec.gov/Archives/edgar/data/40545/000004054523000023/ge-20221231.htm#id3VybDovL2RvY3MudjEvZG9jOjc0MzkxZjNmOTQxODRkOTBhNmRiNWZiYjBhY2NkYjgxL3NlYzo3NDM5MWYzZjk0MTg0ZDkwYTZkYjVmYmIwYWNjZGI4MV83Ni9mcmFnOjVhMzZiODQzYWRmMDQyY2VhZTE5MmFlZjI5MWQyNGM3L3RhYmxlOjk0YjkzYzA3M2IxOTRkMzU4MDVkYzBkZWRhNWEzYmZhL3RhYmxlcmFuZ2U6OTRiOTNjMDczYjE5NGQzNTgwNWRjMGRlZGE1YTNiZmFfOC0xLTEtMS03NjAxNTA_e41603fc-adf5-4580-8511-0334c869878d) · [later](https://www.sec.gov/Archives/edgar/data/40545/000004054524000027/ge-20231231.htm#f-3108) |
| Development | GE / 2021 | 74,196,000,000 | 56,469,000,000 | [earlier](https://www.sec.gov/Archives/edgar/data/40545/000004054523000023/ge-20221231.htm#id3VybDovL2RvY3MudjEvZG9jOjc0MzkxZjNmOTQxODRkOTBhNmRiNWZiYjBhY2NkYjgxL3NlYzo3NDM5MWYzZjk0MTg0ZDkwYTZkYjVmYmIwYWNjZGI4MV83Ni9mcmFnOjVhMzZiODQzYWRmMDQyY2VhZTE5MmFlZjI5MWQyNGM3L3RhYmxlOjk0YjkzYzA3M2IxOTRkMzU4MDVkYzBkZWRhNWEzYmZhL3RhYmxlcmFuZ2U6OTRiOTNjMDczYjE5NGQzNTgwNWRjMGRlZGE1YTNiZmFfOC0yLTEtMS03NjAxNTA_8939912e-c254-40a8-9452-851d7b011400) · [later](https://www.sec.gov/Archives/edgar/data/40545/000004054524000027/ge-20231231.htm#f-3239) |
| Development | GE / 2019 | 95,214,000,000 | 90,221,000,000 | [earlier](https://www.sec.gov/Archives/edgar/data/40545/000004054521000011/ge-20201231.htm#id3VybDovL2RvY3MudjEvZG9jOmQzNDhiNDE0NjBhZDQ4Njc5NjA2ODdlZmEwNGM5OGRmL3NlYzpkMzQ4YjQxNDYwYWQ0ODY3OTYwNjg3ZWZhMDRjOThkZl8xMDMvZnJhZzpjZmFmOTZjZDkwMjM0YTViYTM2MmViZjdmNGViYTcxYi90YWJsZTo3NWUxZmJjNDAyNGY0NDU0OGE2MTdiMDYwMjZlNmViYy90YWJsZXJhbmdlOjc1ZTFmYmM0MDI0ZjQ0NTQ4YTYxN2IwNjAyNmU2ZWJjXzYtMi0xLTEtMA_e0f80bd7-fa4d-497e-b5e1-c26c85ad0879) · [later](https://www.sec.gov/Archives/edgar/data/40545/000004054522000008/ge-20211231.htm#id3VybDovL2RvY3MudjEvZG9jOmUxMDllMzVhMGRjYTQwN2I4ODFlZTQ4NGJiYzM5NzljL3NlYzplMTA5ZTM1YTBkY2E0MDdiODgxZWU0ODRiYmMzOTc5Y184OC9mcmFnOjQ4NTc4ZTQ2OGVhYjQzY2NiYzA0YzNhYmYzYTUxZmVmL3RhYmxlOmFjM2QwNGZhNTI2ZTQ2YjA4ZGM2M2QxNGNhMjBkNjk2L3RhYmxlcmFuZ2U6YWMzZDA0ZmE1MjZlNDZiMDhkYzYzZDE0Y2EyMGQ2OTZfOS0zLTEtMS0xODc4MzE_923b2cf0-c9da-42f9-9f17-2bc5dd8bb306) |
| Development | GE / 2020 | 79,619,000,000 | 75,833,000,000 | [earlier](https://www.sec.gov/Archives/edgar/data/40545/000004054521000011/ge-20201231.htm#id3VybDovL2RvY3MudjEvZG9jOmQzNDhiNDE0NjBhZDQ4Njc5NjA2ODdlZmEwNGM5OGRmL3NlYzpkMzQ4YjQxNDYwYWQ0ODY3OTYwNjg3ZWZhMDRjOThkZl8xMDMvZnJhZzpjZmFmOTZjZDkwMjM0YTViYTM2MmViZjdmNGViYTcxYi90YWJsZTo3NWUxZmJjNDAyNGY0NDU0OGE2MTdiMDYwMjZlNmViYy90YWJsZXJhbmdlOjc1ZTFmYmM0MDI0ZjQ0NTQ4YTYxN2IwNjAyNmU2ZWJjXzYtMS0xLTEtMA_000584d1-38d5-4384-ab2e-b722cc41a809) · [later](https://www.sec.gov/Archives/edgar/data/40545/000004054522000008/ge-20211231.htm#id3VybDovL2RvY3MudjEvZG9jOmUxMDllMzVhMGRjYTQwN2I4ODFlZTQ4NGJiYzM5NzljL3NlYzplMTA5ZTM1YTBkY2E0MDdiODgxZWU0ODRiYmMzOTc5Y184OC9mcmFnOjQ4NTc4ZTQ2OGVhYjQzY2NiYzA0YzNhYmYzYTUxZmVmL3RhYmxlOmFjM2QwNGZhNTI2ZTQ2YjA4ZGM2M2QxNGNhMjBkNjk2L3RhYmxlcmFuZ2U6YWMzZDA0ZmE1MjZlNDZiMDhkYzYzZDE0Y2EyMGQ2OTZfNi0yLTEtMS0xNjg2OTM_3df48d63-77a9-4f7b-9193-9dfcdb8dc687) |
| Development | AAP / 2023 | 11,287,607,000 | 9,209,075,000 | [earlier](https://www.sec.gov/Archives/edgar/data/1158449/000115844924000128/aap-20231230.htm#f-125) · [later](https://www.sec.gov/Archives/edgar/data/1158449/000115844925000064/aap-20241228.htm#f-1382) |
| Development | AAP / 2022 | 11,154,722,000 | 9,148,874,000 | [earlier](https://www.sec.gov/Archives/edgar/data/1158449/000115844924000128/aap-20231230.htm#f-126) · [later](https://www.sec.gov/Archives/edgar/data/1158449/000115844925000064/aap-20241228.htm#f-1383) |

The displayed examples are selected by absolute dollar change, not randomly. Interpretation requires the original accounting-policy, reclassification, disposal and restatement notes. See [source cases](SOURCE_CASES.md) for independently inspected document examples.

## Verification and limitations

The repository contains **13** independently performed AI source checks. They are explicitly labeled as AI work; **independent human review remains pending**. The [review template](SOURCE_REVIEW_TEMPLATE.md) supports a reviewer who did not develop the code. No human accuracy percentage or audit opinion is claimed.

The labeled **synthetic** temporal benchmark records TP=3, FP=0, TN=6, FN=0 over 9 scored cases; 3 refusals are separate. Another 8 / 8 designed semantic scenarios matched their prescribed outcomes. These are checks on named injected faults, not real-world precision/recall estimates. Full inputs and labels are in [the synthetic benchmark](../data/results/synthetic_injection_benchmark.json).

- Arelle supplies general XBRL validation plus the fixed SEC inline transformation module; this is not full EDGAR Filer Manual certification.
- Primary-statement mapping uses explicit concept, dimension, unit and same-role calculation evidence. Unsupported semantics are refused; coverage and refusal reasons remain in the results.
- Growth requires a matching adjacent annual pair in one filing and statement basis, with equal concept namespace/local name and currency. This is a structural comparability check, not certification of unchanged accounting policy. A later filing can update a target year without including its predecessor; such growth queries are refused, not filled from an older basis.
- The twelve issuers form a purposive engineering corpus. Neither observed failure shares nor repeated monthly comparisons estimate a market-wide frequency or a statistically independent sample.
- Revenue updates can be legitimate consequences of business-boundary or accounting-policy changes. Feature differences do not demonstrate excess returns, causal effects, or trading viability.
- Hashes establish byte identity, tests establish specific code properties, and reproductions establish computational consistency. None alone proves accounting truth.

## Reproduction

```console
uv sync --frozen
uv run filingtime verify
uv run filingtime demo
uv run python scripts/reproduce.py --work-dir ./work/reproduction
```

For the full original-filing replay, add `--reparse`. See [validation](VALIDATION.md), [protocol](PROTOCOL.md), and [third-party notices](THIRD_PARTY_NOTICES.md). The raw taxonomy bytes and their notices retain their original terms.
