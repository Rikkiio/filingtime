# Post-evaluation metadata repair: Foot Locker fiscal-year label

The first frozen holdout evaluation **failed closed** during fiscal-year target
construction. It did not produce a first-pass holdout score. The unchanged rules
encountered two Foot Locker filings with the DEI fiscal-year label `2020` but
different period ends. The exact failure, original audit hashes, and absence of
processed holdout outputs are preserved in
[holdout_first_evaluation.json](../data/manifests/holdout_first_evaluation.json).
The original [rule freeze](../data/manifests/rule_freeze.json) remains intact.

## What the source documents establish

| Filing accession | Original DEI fiscal year | Period end | Fiscal year stated in the narrative |
| --- | --- | --- | --- |
| `0000850209-20-000007` | 2020 | 2020-02-01 | 2019 |
| `0000850209-21-000003` | 2020 | 2021-01-30 | 2020 |

In the [first filing's DEI field](https://www.sec.gov/Archives/edgar/data/850209/000085020920000007/fl-20200201x10k.htm#Tc_FyQkErEjgUyvWX7qlcGIxQ_4_1), the original literal is `2020`.
The same document's [FiscalPeriod narrative](https://www.sec.gov/Archives/edgar/data/850209/000085020920000007/fl-20200201x10k.htm#Tb_WtbE2IsyRECi7wwr8E8f0w) explicitly assigns the year ended February 1, 2020 to fiscal year 2019.
Its page footer also labels the annual report as 2019.
The [following filing's FiscalPeriod narrative](https://www.sec.gov/Archives/edgar/data/850209/000085020921000003/fl-20210130x10k.htm#Tb_97oUrfvC9kuTkDXdThw_Dw) assigns fiscal year 2020 to the year ended January 30, 2021 and repeats the prior-period correspondence.

This conclusion comes from the documents' explicit accounting-period descriptions,
not a rule that subtracts one from January or February calendar years. Arelle
faithfully extracted the original DEI values. Generic XBRL validation did not
resolve the disagreement between a structurally valid metadata tag and narrative
financial-year terminology.

## Exactly what may be corrected

[metadata_corrections.json](../data/reference/metadata_corrections.json) contains
one narrowly keyed derived correction: use `2019` as the target fiscal-year label
for accession `0000850209-20-000007`, while retaining its original `2020` value.

Recovery must verify the original audit's SHA-256, the original source bytes'
SHA-256, the cited element ID, and the whitespace-normalized supporting text before
applying that derived label. The correction does not authorize edits to original
HTML/XML, original parsed audits, revenue amounts, financial periods, source
availability times, other accessions, or the frozen research rules. It is not a
general-purpose fiscal-calendar heuristic.

## How to describe the subsequent replay

The correction was created **after observing the first holdout failure**. A replay
using it is a **post-evaluation repaired replay**, not a successful untouched
holdout test. The unchanged original failure must remain alongside any repaired
result; neither its receipt nor the freeze may be silently replaced or recreated.
Actual replay completion and verification belong to the subsequent execution
receipts, not to the existence of this correction file.

The source inspection was performed by a separate AI agent with knowledge of the
observed conflict. It is an independent AI source check, not a blinded check or
independent human sign-off. The correction explicitly records
`untouched_holdout_claim=false` and `human_review_status=pending`.

This case demonstrates a limit of treating regulator-hosted machine-readable
metadata as semantic ground truth: a valid schema, a correct parser, and intact
source hashes can coexist with a conflicting fiscal-year label.

## Reproduce the two distinct paths

The original command still reproduces the recorded conflict:

```console
uv run filingtime normalize --split holdout
```

The explicit recovery command checks the annotation evidence and creates a new
working copy before invoking the frozen normalizer:

```console
uv run filingtime recover-holdout --work-dir ./work/metadata-recovery
```

Recovery accepts identical existing products but refuses to overwrite different
ones. The standard reproduction script exercises both paths in isolated copies,
checks that the original failure did not alter files, and compares the repaired
outputs with the published products. It never replaces the first failure record.
