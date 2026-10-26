# Source and extraction receipts

The corpus contains the original SEC annual filing documents, not reconstructed
HTML or a Companyfacts-only panel. Raw documents are stored with deterministic
gzip compression in `../raw/`. Decompression recovers the downloaded response
bytes without reformatting.

| File | Meaning |
| --- | --- |
| `collection_protocol.json` | Frozen universe rationale, filing window, acceptance cutoff, and availability convention |
| `sources.jsonl` | One record per downloaded SEC URL, with raw and compressed SHA-256, byte counts, path, retrieval time, and role |
| `filings.jsonl` | One record per accession, connecting the primary document, dependencies, SEC acceptance time, and sample split |
| `selection_*.json` | Per-issuer counts before and after the additional UTC acceptance cutoff |
| `identity_*.json` | Current SEC entity identity used to check the stable CIK; sample tickers are historical labels |
| `taxonomy_sources.jsonl` | Unmodified standard taxonomy dependencies needed for offline Arelle parsing |
| `taxonomy_notices.json` | Original taxonomy licensing notices and their hashes |
| `sec_transform_vendor.json` | Exact upstream SEC transform commit, file hashes, and licensing provenance |
| `candidates/*.jsonl` | Unreviewed numeric revenue candidates emitted by Arelle, retaining nonannual and dimensional observations |
| `parsed/*.json` | Per-filing Arelle audit, fiscal-year metadata, calculation edges, presentation roles, and extractor hash |
| `offline_replay_smoke.json` | A real-file replay in a fresh work directory with socket connections forbidden |

`collection_status.json` describes the last *completed invocation*, which may
have selected only a subset. Establish corpus coverage from the frozen universe,
selection records, and accession manifest instead of assuming that this one file
proves completeness.

The SEC `filingDate` window and the UTC `acceptanceDateTime` cutoff are distinct.
Both are applied. `available_at` is acceptance plus 24 hours: a fixed research
convention, not an observed dissemination timestamp or earliest market knowledge.

For older non-inline filings, the original XML instance is the parsing entrypoint;
its URL and hash are attached to its facts. Inline facts point to the original
HTML. The primary narrative filing is preserved in both cases. No facts are
borrowed from another filing when an amendment contains no financial instance.

Standard-taxonomy `retrieved_at` records when a file was archived from Arelle's
cache; the exact HTTP retrieval time was not instrumented. Its URL is the cache's
canonical identity, with HTTPS redirection enabled during retrieval. This is
explicitly different from the observed retrieval times in `sources.jsonl`.

Successful Arelle parsing and generic XBRL validation are not full SEC EFM
certification, accounting comparability assessment, or independent human review.
The official SEC transformation module is used solely for its Inline XBRL value
transformations. Normalization and evaluation are separate stages.
