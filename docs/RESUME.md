# Describing FilingTime on a résumé

Use statements you can explain and reproduce yourself. The source corpus and experiment tables support the scope below; they do not establish investment performance or a human-reviewed accuracy rate.

## 中文

**FilingTime｜历史财务数据的时点重建与前视偏差审计**  
Python · SEC EDGAR · XBRL/Arelle · DuckDB · Parquet · pytest/Hypothesis

- 从 SEC 原始申报构建可追溯财务数据集，覆盖 12 家公司、72 个目标公司财年、87 份年报及修订申报，保存原始文件、字段位置、申报版本及 SHA-256。
- 实现历史时点收入与同比查询，区分财年末提前使用、最终版本回填和当时可用版本；排除分部数据，对口径冲突及未通过同一申报、概念和币种等结构检查的同比明确拒判。
- 采用 8 家开发公司与 4 家原留出公司，保留冻结评估的首次元数据冲突失败，并记录有原文依据的财年标签修复及后续重放；结合性质测试、合成故障注入和原文核对检验时间边界与可复现性。

## English

**FilingTime — Point-in-time financial data reconstruction and look-ahead bias auditing**

- Built a source-linked SEC filing corpus covering 12 issuers, 72 target company-years and 87 annual/amended filings, preserving original bytes, XBRL field locations, filing versions and SHA-256 provenance.
- Implemented historical revenue and growth queries with controlled premature-disclosure and revision-backfill baselines; excluded segment data and refused conflicts or growth inputs failing same-filing, concept and currency checks.
- Preserved the first frozen evaluation's metadata-conflict failure on four reserved issuers after development on eight; documented a source-supported fiscal-year label repair and subsequent replay, alongside property tests, synthetic faults and source checks.

## Be ready to explain

1. Why an unchanged amount from a later filing can still have future-dated provenance.
2. Why a fiscal period end, SEC acceptance time, assumed availability time and retrieval time are different clocks.
3. Why a 10-K/A does not necessarily change revenue, and an ordinary 10-K can change a comparative figure.
4. Why the Coca-Cola investee example is excluded, and why GE's changed comparative revenue is not automatically an accounting error.
5. Why growth can be refused even when both annual amounts exist in the corpus.
6. What a hash, an Arelle check, a Companyfacts match, a synthetic test and a successful CI run each establish—and what they do not establish.
7. Why the first frozen evaluation failed, why the source-supported metadata repair is a post-evaluation annotation, and why unchanged core code does not restore an untouched-holdout claim.

The numerical findings and their denominators belong in the [research report](REPORT.md). The [validation evidence](IMPLEMENTATION_STATUS.md) records what was actually run. Independent human accounting review remains pending. Do not describe AI source checks as human annotations, claim a market-wide error rate from this selected sample, or claim a Sharpe-ratio improvement from this data audit.
