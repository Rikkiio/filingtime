# Source-based case studies

These cases were checked by a separate AI validation agent against original filing HTML, displayed financial-statement rows, and embedded contexts or the original XML instance. They are **independent AI source checks, not independent human review or audit sign-offs**. Human review is pending.

The machine-readable observations are in [source_checks.jsonl](../data/reference/source_checks.jsonl). Each record keeps the original URL, uncompressed file SHA-256, displayed amount and scale, expected decimal value, exact period, context, fact locator, reviewer origin and subsequent program-comparison status. Program-comparison results are tied to the specific artifact hash recorded there; a pending comparison is not a passed check.

## 1. Apple: the period end is not the disclosure time

The [2019 consolidated statement of operations](https://www.sec.gov/Archives/edgar/data/320193/000032019319000119/a10-k20199282019.htm#d175206359e883-wk-Fact-7C6E0A97AB444AD69F72FE3FF1550DF5) labels its units as millions, with exceptions for share items. The total net sales line reports:

| Fiscal period | Displayed total net sales | USD after scale conversion | Source context |
|---|---:|---:|---|
| 2018-09-30 to 2019-09-28 | 260,174 million | 260,174,000,000 | `FD2019Q4YTD` |
| 2017-10-01 to 2018-09-29 | 265,595 million | 265,595,000,000 | `FD2018Q4YTD` |

The exact amounts come from the total row, not the separate products and services lines. Both embedded contexts identify Apple's CIK and have no segment dimensions. The same-filing arithmetic change is approximately **−2.04%**. This is revenue growth, not a stock return or a claim about constant-business-scope growth.

The filing metadata records acceptance at `2019-10-30T22:12:36Z`. Under the fixed 24-hour convention, the allowed time is `2019-10-31T22:12:36Z`. A query one second before that allowed time must refuse this filing; making the number available at the September fiscal period end uses future information under the project's rule. The convention does not establish the true first market publication time.

Review transparency: the parent implementation agent had reported the FY2019 CLI amount before the validation agent inspected the source. That record explicitly sets `prior_system_value_exposure=true`; it must not be described as a blinded numeric check. The source, scale, period and exact context were nevertheless inspected directly.

## 2. Microsoft: a new source version need not change the number

The [2019 income statement](https://www.sec.gov/Archives/edgar/data/789019/000156459019027952/msft-10k_20190630.htm#INCOME_STATEMENTS) reports total revenue of **125,843 million USD** for the year ended June 30, 2019, and **110,360 million USD** for the prior year. The revenue total combines the displayed product and service/other lines. The 2019 HTML is not inline XBRL; the matching original XML-instance facts are `F_000028` and `F_000029`, with separate annual contexts.

The [2020 income statement](https://www.sec.gov/Archives/edgar/data/789019/000156459020034944/msft-10k_20200630.htm#F_000049) reports **143,015 million USD** for FY2020 and repeats **125,843 million USD** for FY2019. The FY2019 comparative in that later filing is fact `F_000050`.

The repeated FY2019 number is unchanged in these two inspected filings. Selecting the 2020 source version at a date before it was available would still use future provenance, even though the numerical revenue difference is zero. This is why the experiment reports future-version use separately from numerical distortion. These two documents do not demonstrate a changed-value restatement.

The source checks were recorded from the original primary statement rows before consulting their normalized outputs. Each monetary value was multiplied by the displayed million-unit scale and matched to its exact period/context. This limited check does not certify every accounting policy or every version of Microsoft's filings.

## 3. Coca-Cola: the largest revenue-like number is the wrong entity scope

The [2019 consolidated income statement](https://www.sec.gov/Archives/edgar/data/21344/000002134420000006/a2019123110-k.htm#d32419075e929-wk-Fact-34674A669526AB24D8FB304BB900252B) reports **37,266 million USD** of net operating revenues; its FY2018 comparison is **34,300 million USD**.

A [separate equity-method-investee table](https://www.sec.gov/Archives/edgar/data/21344/000002134420000006/a2019123110-k.htm#d32432990e1023-wk-Fact-92351A2D7895AF8290D918014944F413) reports **75,980 million USD** for 2019. The surrounding paragraph identifies this as aggregate financial information for equity method investees. Its concept is `EquityMethodInvestmentSummarizedFinancialInformationRevenue`, and its context includes the investee-name axis and `OtherEquityMethodInvesteesMember`.

The larger number is not Coca-Cola's consolidated revenue. A keyword search followed by “take the maximum” would therefore choose an incorrect amount. The reference record marks it as an expected dimensional/scope exclusion, keeping the source number as evidence rather than treating it as a revenue revision.

This is a real source-backed negative example. It is separate from the synthetic injected faults used in the unit tests.

## 4. GE: later comparative revenue changes with retrospective presentation

The [original FY2019 consolidated statement](https://www.sec.gov/Archives/edgar/data/40545/000004054520000009/ge10-k2019.htm#d44569710e3132-wk-Fact-F4068053672FE1794CF64D42DDA9BCB4), filed in 2020, reports **95,214 million USD** of total revenue for January 1–December 31, 2019. The [2021 annual report filed in 2022](https://www.sec.gov/Archives/edgar/data/40545/000004054522000008/ge-20211231.htm) presents **90,221 million USD** for the same FY2019 period in its primary statement of earnings. Both source contexts have GE's CIK, the same dates, USD units, million scaling, and no segment dimensions. These two inspected versions differ by **4,993 million USD**.

This is evidence of a changed historical comparative, not by itself evidence of a financial error. [Note 1, Financial Statement Presentation](https://www.sec.gov/Archives/edgar/data/40545/000004054522000008/ge-20211231.htm#ie109e35a0dca407b881ee484bbc3979c_2047), explains that GE moved from three-column to one-column reporting for all presented periods after the GECAS/AerCap transaction. It also moved amounts related to EFS, Working Capital Solutions and Treasury from the former GE Capital service-revenue line to Other income; run-off Insurance revenue remained in revenue. Note 2 describes retrospective discontinued-operation presentation including GECAS. The source check has **not reconciled the entire 4,993-million difference component by component**. It therefore does not attribute the whole change to GECAS or classify it as an error correction. A separate spare-parts reclassification described in Note 1 changes the equipment/services split without changing total revenue.

The first source was accepted at `2020-02-24T21:34:07Z`; the later one at `2022-02-11T13:33:15Z`. Under the project's convention, the later comparative cannot enter a historical PIT snapshot before `2022-02-12T13:33:15Z`. Backfilling that source into 2020 would change the value and use future information. The full cutoff-bounded corpus may contain additional intervening or subsequent versions; this two-source illustration does not claim these are the only versions or the final cutoff value.

The two machine-readable records preserve the exact primary-table fact IDs, source hashes and explanatory-note locator. Both explicitly mark prior value exposure because the parent agent supplied the observed amounts before this source inspection. They are independently read source checks, not blinded checks or human sign-offs.

## 5. Advance Auto Parts: an amendment does not automatically change revenue

The [original FY2023 statement of operations](https://www.sec.gov/Archives/edgar/data/1158449/000115844924000048/aap-20231230.htm#f-129) and the [amended statement](https://www.sec.gov/Archives/edgar/data/1158449/000115844924000128/aap-20231230.htm#f-125) both report net sales of **11,287,607 thousand USD**, or **11,287,607,000 USD**, for January 1–December 30, 2023. Their current-year facts use the same undimensioned `c-1` annual context, CIK, concept and monetary scale.

The amendment's [Explanatory Note](https://www.sec.gov/Archives/edgar/data/1158449/000115844924000128/aap-20231230.htm#id9e0cd817b8a44ff88936ad275a70d3e_7) describes an additional material weakness in internal control, changes to the control conclusions and related audit reports, and errors the issuer assessed as immaterial. It explicitly says the annual consolidated financial statements are not being restated. This is an issuer disclosure about the amendment's scope, not an independent audit conclusion from this project. The unchanged current-year revenue was also verified directly in both primary tables.

The original filing was accepted at `2024-03-12T20:28:41Z`; the amendment at `2024-05-30T01:01:16Z`. It is still a distinct later source version, even though the checked revenue is numerically unchanged. A detector that labels every 10-K/A as a revenue change would manufacture a change here. Both source records mark prior value exposure and pending human review; program comparison is separately recorded.

## Scope of the evidence

The thirteen records demonstrate source traceability, a real scope trap, a timing boundary, unchanged comparative values, a changed historical comparative accompanied by presentation notes, and an amendment with unchanged current-year revenue. They do not establish population-wide extraction accuracy, independent human agreement, or that later numerical changes are accounting errors. Twelve records describe consolidated totals; one is an expected scope exclusion. Comparison status applies only to the artifact hashes recorded with each check.

An independent person can use [SOURCE_REVIEW_TEMPLATE.md](SOURCE_REVIEW_TEMPLATE.md) to review these same records and record disagreements. No human sign-off is presently asserted.
