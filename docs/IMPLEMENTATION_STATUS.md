# Release evidence

The local full reproduction completed on **2026-10-26 UTC** with **202 tests passed**. It replayed all **87 original filings** with network access blocked, compared every extracted candidate field, regenerated the experiments and report, exercised the CLI and Parquet store, and built and installed the wheel in a separate interpreter. The complete, unchanged execution receipt is [release_reproduction.json](../data/manifests/release_reproduction.json).

| Requirement | Observed result | Evidence |
|---|---|---|
| Original filing collection | 12 issuers; 87 filings; 800 SEC source files | [Collection integrity](../data/manifests/collection_integrity.json) |
| Source and dependency integrity | All 800 SEC files, 174 taxonomy files, 4 vendor files and 2 notices verified | [Integrity receipt](../data/manifests/collection_integrity.json) |
| Planned sample accounting | 48 development and 24 metadata-repaired target company-years; no missing planned targets | [Coverage](../data/results/source_coverage.json) |
| First frozen evaluation | **Failed closed**, before normalization outputs, on conflicting Foot Locker fiscal-year metadata | [Original failure](../data/manifests/holdout_first_evaluation.json) |
| Explicit subsequent recovery | Source-supported one-field metadata annotation; **post-evaluation repaired replay**, not untouched holdout success | [Recovery receipt](../data/manifests/holdout_recovery.json), [explanation](POST_EVALUATION_REPAIR.md) |
| Frozen computational rules | Original rule hashes unchanged; original raw documents and parsed audits preserved | [Freeze record](../data/manifests/rule_freeze.json) |
| Extraction cross-check | 171 development + 87 repaired unique source facts exactly match the separate SEC Companyfacts extraction | [Development](../data/results/development_companyfacts_crosscheck.json), [repaired replay](../data/results/holdout_companyfacts_crosscheck.json) |
| Automated tests | **202 passed** in the full local run | [Execution receipt](../data/manifests/release_reproduction.json) |
| Offline source replay | **87 / 87** filings reproduce all candidate fields; zero Arelle errors | [Parser section of receipt](../data/manifests/release_reproduction.json) |
| Original failure and repaired replay reproduction | Exact failure reproduced; repaired outputs byte-identical; original evidence unchanged | [Recovery section of receipt](../data/manifests/release_reproduction.json) |
| Experiment and report reproduction | Six experiment artifacts and three report text artifacts reproduce byte-for-byte; PNG/SVG regenerated and validated | [Execution receipt](../data/manifests/release_reproduction.json) |
| Package installation | Offline wheel build; fresh no-dependency install, core query and CLI version smoke check; full dependency integration tested in the locked environment | [Wheel section of receipt](../data/manifests/release_reproduction.json) |
| Windows / Linux continuous integration | Actual runs and conclusions are published by GitHub; use the linked job results as the authority | [Workflow history](https://github.com/Rikkiio/filingtime/actions/workflows/ci.yml) |
| Independent human accounting review | **Pending** | [Review template](SOURCE_REVIEW_TEMPLATE.md) |

The local full reproduction took approximately 494 seconds on the tested machine. Timing is descriptive, not a performance benchmark. Cross-platform CI runs the default reproduction, which includes one real offline parser specimen; the local receipt above records the separate all-87 replay.

The source checks and fiscal-year annotation are explicitly attributed AI work. They do not establish a human-reviewed accuracy rate. The repaired sample remains labeled as repaired even when its reproduction and CI checks pass. Numerical findings and their denominators are in the [research report](REPORT.md); résumé wording is in [RESUME.md](RESUME.md).
