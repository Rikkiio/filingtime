# Third-party notices and source-data terms

The repository's [MIT license](../LICENSE) covers original FilingTime code and documentation. It does **not** replace copyright notices or terms attached to vendored code, SEC filing documents, accounting taxonomies, XBRL schemas, or installed dependencies. Original source notices and license files are retained.

## Component inventory

| Material | Location / provenance | Applicable notices |
|---|---|---|
| Arelle processor | Installed `arelle-release` dependency, pinned by `uv.lock` | Apache License 2.0, copyright Workiva, Inc.; bundled dependencies can have additional terms |
| SEC inline transformation module | `src/filingtime/_vendor/sec_transform/__init__.py` | Original U.S. SEC staff/government-work notice; module metadata declares `Apache-2`; preserve both; full Apache text in the same directory as `APACHE-2.0.txt` |
| Text-to-number helper | `src/filingtime/_vendor/sec_transform/text2num.py` | MIT, copyright 2008 Greg Hewgill; complete notice retained in source |
| Upstream EDGAR repository license | `src/filingtime/_vendor/sec_transform/LICENSE` | Upstream CC0-1.0 text; this does not erase file-specific notices |
| Issuer filings and SEC metadata | `data/raw/<CIK>/`; `data/manifests/sources.jsonl` | Original filings and source notices; SEC access/reuse policy applies |
| FASB US-GAAP taxonomy | Relevant files under `data/raw/taxonomy/` | FASB/FAF Authorized Uses notice, retained source copyrights and third-party terms |
| SEC Reporting Taxonomy (SRT) | Relevant files under `data/raw/taxonomy/` | Separate FASB SRT Authorized Uses notice and retained source copyrights |
| XBRL and other taxonomy dependencies | Relevant files under `data/raw/taxonomy/` | Notices in each original schema/document; no blanket MIT relicense |

The exact SEC-transform upstream revision and file hashes are in [sec_transform_vendor.json](../data/manifests/sec_transform_vendor.json). The copied module is limited to inline numeric transformations. Its presence is not a claim that FilingTime implements or passes the entire EDGAR Filer Manual validation suite.

## Arelle and the pinned transformation sources

Arelle's [official license page](https://arelle.readthedocs.io/en/latest/license.html) identifies Apache License 2.0 for the core and expressly notes additional dependency/plugin terms. See the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) for its full conditions.

The SEC transformation files are copied from [Arelle/EDGAR revision 4891c4c9889c77af247428ceff4fa7cc52d534ea](https://github.com/Arelle/EDGAR/tree/4891c4c9889c77af247428ceff4fa7cc52d534ea). The module's government-work header, its Apache declaration, the helper's MIT notice, and the upstream repository's CC0 license are retained as they appear upstream rather than being collapsed into a single inferred license.

The module header refers to `COPYRIGHT.md`, but that file is absent from this pinned upstream tree. FilingTime does not invent a substitute or claim the dangling reference was resolved. The repository's provenance record documents this upstream condition.

## SEC filings and automated access

The [SEC webmaster FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions) states that government-created site content and public EDGAR filings are free to access and reuse. Its [website dissemination and access policy](https://www.sec.gov/about/privacy-information) provides the surrounding terms. FilingTime preserves the original issuer documents and source links and does not claim to own or relicense issuer-authored content.

Downloaders should supply an identifiable user agent and respect the SEC's access limits. A user's private contact details are configuration, not repository content. No SEC endorsement of FilingTime is implied.

## FASB/FAF taxonomy notices

The project includes unchanged taxonomy bytes to support reproducible interpretation of the filings. Compression changes storage, not the uncompressed source bytes; both hashes are recorded. Their copyright headers must remain intact, and the project's MIT license does not apply to them.

Two distinct official notices govern the included taxonomy families:

- [US-GAAP Financial Reporting Taxonomy: Authorized Uses](https://xbrl.fasb.org/terms/TaxonomiesTermsConditions.html), with the [downloaded original HTML](../data/raw/taxonomy/notices/FASB_TaxonomiesTermsConditions.html).
- [SEC Reporting Taxonomy: Authorized Uses](https://xbrl.fasb.org/terms/SRT_TermsConditions.html), with the [downloaded original HTML](../data/raw/taxonomy/notices/FASB_SRT_TermsConditions.html).

The notices permit unchanged incorporation in works that explain or assist use/implementation and require inclusion of the Authorized Uses notice on the first page of such a distributed work. They prohibit unauthorized modifications and retain additional third-party rights. The repository front page must therefore carry both complete notices in addition to these links. See the original notices for their exact terms, warranty disclaimers and limitations of liability.

The original notice bytes and source hashes are recorded in [taxonomy_notices.json](../data/manifests/taxonomy_notices.json). Copyright years are preserved as supplied by the source, without treating them as a project release date. Files imported from XBRL International or other third parties retain their own notices; the FASB notice does not replace them.

## Redistribution checklist

When copying or packaging this project, retain:

1. The project's own license, scoped to its original contributions.
2. Vendored source headers, the complete upstream license texts, and provenance manifest.
3. Unchanged taxonomy files with original headers and both complete FASB Authorized Uses notices on the distribution's first page.
4. The source manifests and raw-data attribution.
5. Any notices required by dependencies that you redistribute, rather than merely install separately.

This inventory describes included materials and preserves their stated terms. It is not a new license grant from their respective owners.
