# Implementation status

The authoritative completion evidence will be test receipts, corpus manifests, generated
experiment results, the rule-freeze record, and the published GitHub commit and Actions run.

| Requirement | Current state |
|---|---|
| Protocol and 8/4 split | Specified before held-out values |
| Original filing collection | Development 57 filings complete; held-out bytes collecting |
| Arelle extraction and semantic mapping | All 57 development filings parsed; 48 planned target years identified |
| Temporal engine and append-only store | Implemented; temporal and persistence tests passing |
| Independent adversarial tests | 143 tests passed in latest local full run; release run still required |
| Held-out evaluation | Not started |
| Human reference review | Pending external reviewer |
| CLI, reproducible experiment, report | Implemented; development experiment generated; final report awaits held-out evaluation |
| Clean-environment validation | Not started |
| GitHub publication | Not started |
