# Independent source-review record

Copy this template for a real review. All example fields below are deliberately empty. This file contains no empirical values, completed reviews, signatures, or reviewer endorsements.

Use the original report and [annotation guide](ANNOTATION_GUIDE.md). Record an initial source-based answer before inspecting the program's output, then compare the two in a separate step. If the reviewer already saw the output, set the blindness field to `false` and describe that limitation.

## Review record

```json
{
  "schema_version": "filingtime-source-review-v1",
  "record_id": null,
  "record_status": "template_not_a_completed_review",
  "sample_split": null,
  "issuer": {"cik": null, "name": null},
  "filing": {
    "accession": null,
    "form": null,
    "original_url": null,
    "raw_relative_path": null,
    "raw_sha256": null,
    "acceptance_timestamp_source": null,
    "accepted_at_utc": null,
    "available_at_utc": null,
    "availability_convention": "acceptance_plus_24_elapsed_hours"
  },
  "source_observation": {
    "statement_title": null,
    "table_or_section_locator": null,
    "fact_anchor_or_line_locator": null,
    "displayed_line_label": null,
    "displayed_amount": null,
    "displayed_scale": null,
    "unit": null,
    "normalized_decimal_value": null,
    "reporting_precision": null,
    "period_start": null,
    "period_end": null,
    "annual_period_rationale": null,
    "entity_scope": null,
    "concept_qname": null,
    "concept_namespace": null,
    "context_id": null,
    "dimensions": null,
    "accounting_basis_evidence": null
  },
  "comparison": {
    "previous_period_start": null,
    "previous_period_end": null,
    "previous_amount": null,
    "previous_fact_locator": null,
    "previous_concept_qname": null,
    "previous_concept_namespace": null,
    "same_filing": null,
    "unit_compatible": null,
    "basis_compatible": null,
    "concept_namespace_and_local_name_equal": null,
    "supporting_note_locator": null,
    "change_classification": null,
    "comparability_decision": "pending"
  },
  "historical_query": {
    "as_of_utc": null,
    "eligible_accessions": null,
    "selected_accession": null,
    "selection_reason": null,
    "reference_decision": "pending"
  },
  "program_comparison": {
    "code_commit": null,
    "rule_freeze_hash": null,
    "output_artifact": null,
    "reference_recorded_before_output_view": null,
    "value_agreement": null,
    "semantic_agreement": null,
    "version_agreement": null,
    "disagreement_description": null
  },
  "review": {
    "annotation_origin": null,
    "ai_assistance_description": null,
    "independent_human_review_status": "pending",
    "reviewer_public_id": null,
    "reviewer_role": null,
    "reviewer_independent_of_implementation": null,
    "reviewed_at_utc": null,
    "decision": "pending",
    "review_evidence_url_or_relative_path": null
  }
}
```

## Acceptance questions for the reviewer

| Check | Evidence to inspect | Result to record |
|---|---|---|
| Document identity | URL, accession and original-byte hash | Match, mismatch or unresolved |
| Amount | Printed line, currency/scale and XBRL fact | Displayed and normalized decimal values |
| Scope | Consolidated statement, entity and dimensions | Consolidated total, component or unresolved |
| Period | Original start/end dates and statement heading | Annual, transition, quarter or unresolved |
| Comparability | Same-filing adjacent-year column, concept namespace/local name, currency, statement basis and explanatory notes | Structural checks and economic interpretation recorded separately |
| Historical selection | Acceptance evidence and fixed availability convention | Eligible version or explicit refusal |
| Program comparison | Saved output from the frozen code | Agreement by value, semantics and version separately |

Only an actual independent human may change `independent_human_review_status` from `pending` to `completed`. An AI-assisted source extraction can be recorded as `annotation_origin: "ai_assisted_source_check"`; it must not populate a human sign-off. A disagreement remains visible until source-based adjudication is recorded.

## Human sign-off

Reviewer public identifier: **not yet supplied**  
Review date/time: **not yet supplied**  
Independence from implementation: **not yet established**  
Decision and reviewed record IDs: **pending**  
Signed review evidence: **not yet supplied**

A real sign-off should identify the exact reviewed records, code/input versions and remaining disagreements. Do not place private contact details or a fabricated signature into the public repository.
