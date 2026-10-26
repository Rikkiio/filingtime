# Research protocol v1

Status: specification fixed before financial-value inspection of held-out firms.
This is a small engineering challenge corpus, not a representative market sample.

## Question

Can a reader reconstruct the annual consolidated revenue allowed at a historical query
time from original filings, and identify feature distortion from premature availability
or later-version backfilling?

## Scope and sample

- US-GAAP nonfinancial issuers; consolidated annual revenue and year-on-year growth only.
- Target fiscal years 2019–2024. Earlier comparative periods may support growth.
- Filing collection cutoff: 2025-12-31T23:59:59Z. Forms 10-K and 10-K/A only.
- Development: AAPL, MSFT, KO, CAT, GE, NKE, AAP, GPRO.
- Held out: COST, DE, HPQ, FL. Fetch bytes without inspecting financial values until the
  rule-freeze record is written. Company CIK, not ticker, is the stable identifier.
- The purposive sample spans business models, size and fiscal calendars. GE is a known
  business-boundary challenge; it is not evidence of a market-wide error frequency.
- Later annual filings within cutoff can disclose earlier comparative-period versions.
  A /A form does not itself imply a revenue change.

## Time convention

Preserve economic period, SEC acceptance timestamp, retrieval timestamp, and allowed
availability separately. Normalize timestamps to UTC. The research availability convention
is acceptance plus 24 elapsed hours. This is a fixed conservative modeling assumption,
not a measurement or guarantee of public dissemination or investor receipt.
An eligible version must satisfy `available_at <= as_of`. SEC 8-K announcements and other
earlier public information are outside this collection; no first-market-knowledge claim.

## Semantic contract

Keep original concept, context, dimensional scope, unit, period, displayed label, source
location and provenance. Do not silently equate dimensional segment data with entity revenue.
Distinguish numerical updates from accounting restatements: reclassification, accounting
policy and discontinued operations may change comparatives legitimately. Unknown semantics
must remain unverified or refused, with a machine-readable explanation.
Growth admission requires an adjacent annual pair within the same filing and statement
basis, with equal concept local name, concept namespace and currency. Different concept
names are not silently treated as accounting synonyms. These are structural comparability
checks, not proof that every accounting-policy detail is unchanged; independent accounting
review remains pending. Ambiguous or unsupported duration/unit/basis combinations are refused.

## Three modes

1. `period_end`: move only the first disclosed version's effective timestamp back to
   fiscal period end. Later revisions retain their actual availability timestamps.
   After the first actual availability, selected revenue equals PIT. This isolates
   premature first-disclosure exposure without also freezing stale first values.
2. `latest`: final version in the fixed collection, made usable from the first eligible
   original disclosure date. This isolates later-version backfilling.
3. `pit`: only versions eligible at the query time, preserving all source versions.

Use identical target company-period-query keys and the same growth formula. Report future
use, numeric differences and direction changes separately. Rank comparisons use a declared
common evaluable set; missing/refused cases and denominators remain visible. The rank metric
describes this small sample and is not portfolio-return evidence.

This timing definition was clarified before any held-out financial values were opened;
see [amendment 01](PROTOCOL_AMENDMENT_01.md). Superseded development exploration is retained.

## Freeze and evaluation

Before held-out parsing, write the code and mapping hashes and development validation
receipt to `data/manifests/rule_freeze.json`. Do not tune on held-out outcomes and continue
calling them untouched. Any post-evaluation correctness repair must be disclosed and the
affected evaluation relabeled accordingly. Independently selected stress examples remain
separate from the frozen evaluation.

## Evidence and release gates

- Every accepted fact must retain accession, raw URL, raw SHA-256, fact/context/concept
  identifiers and a source anchor or explicit fallback locator.
- Fixed raw corpus and lockfile; offline source-hash verification and executable demo.
- Property tests: future-append invariance for PIT, no early visibility, unchanged
  amendments, unit/period/dimension conflicts, and incompatible-growth refusal.
- Fault injection is labeled synthetic. Real cases include links and exact source facts.
- Cross-check extraction separately from accounting semantics. Arelle validation, SEC
  extracted facts, a file hash and CI each support different claims.
- Reference records identify their creator and evidence. AI-assisted source checks are
  not independent human annotations. Human review status remains `pending` unless a
  real independent person supplies review evidence. No invented agreement rate.
- Publish coverage/refusal/error counts, held-out status, failures, corpus limitations,
  and the exact commands needed to reproduce all reported numbers.
- Clean-environment install, tests, CLI demo, corpus verification, experiment and report
  regeneration must run successfully before a completed release is claimed.
- GitHub upload and remote commit/file/Actions verification are required for delivery.

## Sources

- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/about/webmaster-frequently-asked-questions
- https://arelle.org/arelle/documentation/
- https://www.xbrl.org/the-standard/what/key-concepts-in-xbrl/validation/
