# Source-based revenue annotation

This guide creates reviewable reference labels for annual consolidated revenue and its disclosure versions. It is a procedure, not a claim that human review has already occurred. Current independent human-review status is **pending** unless an attached dated reviewer record supersedes it.

The empty [source-review template](SOURCE_REVIEW_TEMPLATE.md) supplies the fields and sign-off record for a reviewer. It contains no completed annotations.

## Review unit

One annotation concerns one fact in one original filing: issuer CIK, accession, economic start/end dates, revenue definition, unit, value and source location. A historical-query reference also records the query instant and which version is eligible under acceptance plus 24 elapsed hours.

The source is the original 10-K/10-K/A document and its contexts/notes. SEC Companyfacts and system output can be comparison tools, but should not replace reading the source. To keep a reference independent, record the label before seeing the program's answer.

## Record these fields

| Field group | Required contents |
|---|---|
| Identity | Stable annotation ID, CIK, accession, form type |
| Raw evidence | Original URL, local relative path, SHA-256, table/section/anchor and context ID |
| Economic scope | Period start/end, annual-period rationale, consolidated/segment scope, accounting basis |
| Number | As-displayed number, scale, sign, unit, normalized decimal value, reporting precision |
| XBRL | Concept qualified name and namespace URI, fact ID, context and dimensions, unit reference |
| Time | Source acceptance timestamp with zone, normalized UTC, convention-derived availability, optional query time |
| Comparability | Prior-year source and period, unit/basis/concept-identity agreement, explanatory-note evidence, decision |
| Change explanation | No change, error correction, reclassification, policy change, business-boundary change, tagging difference, or unresolved |
| Decision | Accepted, excluded, ambiguous or unresolved; explicit reason |
| Review | Annotator role/identity, timestamp, blinded-to-program flag, review status, dispute resolution |

Use decimal arithmetic for money. Preserve the displayed and normalized values; a scale such as “in millions” is part of the source evidence, not an arbitrary tolerance. A number repeated in a note may have different context from the main statement.

## Annotation steps

1. Verify the raw-file hash and accession against the manifest. Open the original document and identify the consolidated income/operations statement.
2. Identify the total annual revenue line. Record its printed label, amount, currency and scale. If several totals are plausible, inspect the accounting note and preserve the ambiguity.
3. Match that line to its XBRL fact/context. Check the reporting entity, exact start/end dates, period length, unit and dimension members. An absence of dimensions is useful evidence, but does not by itself prove the line is the intended total.
4. Record why it is an annual fiscal period. Fiscal years need not end in December and may span 52 or 53 weeks. Quarterly, year-to-date and transition periods must not become annual observations solely because they share an end date.
5. Inspect prior-year comparative columns and relevant accounting-policy, restatement, reclassification and discontinued-operation notes. A later filing may alter prior periods without using form 10-K/A.
6. For growth, require the current and preceding fiscal-year amounts from the same filing, with equal currency, statement basis, concept namespace and concept local name. A prefix alias does not change concept identity; a different concept must not be assumed synonymous. These structural checks help preserve a common presentation basis but do not prove constant business scope or unchanged policy. Record the supporting notes and any unresolved semantic interpretation separately.
7. For a historical query, list eligible filing versions, apply the predeclared availability rule and record the selected version or refusal. Later evidence can explain a change but cannot be used as if it had already been disclosed.
8. Save the initial annotation and review history without overwriting disagreements. Have a different person independently reproduce the critical fields if human validation is claimed.

## Difficult and negative cases

- **Amendment with no income-statement change:** do not invent a new revenue fact merely because the form has `/A`.
- **Later comparative recast:** distinguish a restatement correcting an error from a change in presentation or business scope. Record the note that supports the classification; otherwise mark the reason unresolved.
- **Conflicting duplicates:** same period, unit and semantic scope with materially different values requires investigation. Do not resolve a conflict through file ordering, a maximum or a sum without source support.
- **Custom concepts:** a familiar substring such as “Revenue” is not sufficient. Require a source-linked mapping to the consolidated total; unsupported concepts remain unsupported.
- **Segment facts:** do not add segments unless the project explicitly implements and validates a complete reconciliation including eliminations. This release's target is the disclosed consolidated total.
- **Changed currency, period or basis:** keep the observations but refuse the unsupported comparison. Do not silently convert currencies or annualize a short period.
- **Missing data:** distinguish source unavailable, fact absent, parse failure, unsupported semantics and ambiguous evidence. None of these is a zero revenue.

## Review status vocabulary

| Status | Meaning |
|---|---|
| `development_annotation` | Used by the implementation team to design or debug rules |
| `ai_reviewed` | Another AI process reviewed the evidence; not a human judgment |
| `human_review_pending` | Independent human review has not occurred |
| `human_independently_reviewed` | A documented independent person checked the original evidence |
| `disputed` | Reviewers disagree; label must not be treated as settled truth |
| `adjudicated` | Disagreement resolved with preserved evidence and a recorded decision |

A self-authored answer, CI pass or agreement with Companyfacts does not upgrade a label to `human_independently_reviewed`. Never publish a reviewer's private contact information without permission; a stable public reviewer ID and the review method are sufficient.

## Source references

- [SEC API scope and extracted-fact limitations](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
- [SEC timestamps and availability FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions).
- [XBRL validation and the limits of rule checking](https://www.xbrl.org/the-standard/what/key-concepts-in-xbrl/validation/).
