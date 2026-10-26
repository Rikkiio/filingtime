"""Arelle-backed extraction of unreviewed revenue candidates from source bytes.

Extraction does not establish accounting comparability. Every emitted candidate
starts ambiguous and must pass the separately versioned normalization rules.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from filingtime.ingest import load_jsonl, read_source, sha256, utc_now
from filingtime.models import RevenueFact

REVENUE_PATTERN = re.compile(r"revenue|net\s*sales|sales\s*revenue|total\s*sales|turnover", re.IGNORECASE)


def unpack_filing(root: Path, filing: dict[str, Any], work_dir: Path) -> Path:
    """Materialize verified bytes together so relative XBRL references resolve."""
    sources = {r["url"]: r for r in load_jsonl(root / "data/manifests/sources.jsonl")}
    folder = work_dir / "extracted" / filing["accession"]
    folder.mkdir(parents=True, exist_ok=True)
    for file in filing["files"]:
        record = sources[file["url"]]
        data = read_source(root, record)
        target = folder / Path(record["local_path"]).stem
        if not target.exists() or sha256(target.read_bytes()) != record["sha256"]:
            target.write_bytes(data)
    return folder


def _entrypoint(folder: Path, filing: dict[str, Any]) -> Path:
    if filing["is_inline_xbrl"]:
        return folder / filing["primary_document"]
    # Pre-inline filings contain their original XML instance as a separate file.
    from lxml import etree
    for candidate in sorted(folder.glob("*.xml")):
        if candidate.name.lower().endswith(("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")):
            continue
        try:
            node = next(etree.iterparse(str(candidate), events=("start",), resolve_entities=False))[1]
            if node.tag == "{http://www.xbrl.org/2003/instance}xbrl":
                return candidate
        except (etree.XMLSyntaxError, StopIteration):
            continue
    # Amendments sometimes contain no financial XBRL. Preserve the explicit
    # no-instance result instead of borrowing values from another filing.
    return folder / filing["primary_document"]


def _role_index(model: Any) -> dict[Any, list[str]]:
    from arelle import XbrlConst
    output: dict[Any, set[str]] = {}
    relationships = model.relationshipSet(XbrlConst.parentChild)
    for relation in relationships.modelRelationships:
        role = relation.linkrole
        definitions = model.roleTypes.get(role, [])
        definition = definitions[0].definition if definitions else ""
        role_label = role + (" | " + definition if definition else "")
        for concept in (relation.fromModelObject, relation.toModelObject):
            output.setdefault(concept, set()).add(role_label)
    return {concept: sorted(roles) for concept, roles in output.items()}


def _accounting_relationships(model: Any) -> dict[str, Any]:
    """Expose presentation and calculation evidence, without picking a total."""
    from arelle import XbrlConst
    role_names = {role: entries[0].definition or "" for role, entries in model.roleTypes.items() if entries}
    statement_pattern = re.compile(r"statement.*(income|operations|earnings)|consolidated.*(income|operations|earnings)", re.IGNORECASE)
    income_roles = {role for role, name in role_names.items() if statement_pattern.search(name) and not re.search(r"comprehensive|parenthetical|detail|note", name, re.IGNORECASE)}
    concepts = []
    seen = set()
    for relation in model.relationshipSet(XbrlConst.parentChild).modelRelationships:
        if relation.linkrole not in income_roles:
            continue
        for concept in (relation.fromModelObject, relation.toModelObject):
            if concept is not None and (relation.linkrole, str(concept.qname)) not in seen:
                seen.add((relation.linkrole, str(concept.qname)))
                concepts.append({"role": relation.linkrole, "concept": str(concept.qname), "label": concept.label(lang="en-US") or ""})
    edges = []
    for relation in model.relationshipSet(XbrlConst.summationItem).modelRelationships:
        parent, child = relation.fromModelObject, relation.toModelObject
        if parent is None or child is None:
            continue
        names = str(parent.qname) + " " + str(child.qname)
        if relation.linkrole not in income_roles and not REVENUE_PATTERN.search(names):
            continue
        edges.append({"from_concept": str(parent.qname), "to_concept": str(child.qname), "weight": str(relation.weight), "role": relation.linkrole})
    return {"presentation_roles": role_names, "income_statement_concepts": sorted(concepts, key=lambda x: (x["role"], x["concept"])), "calculation_edges": sorted(edges, key=lambda x: (x["role"], x["from_concept"], x["to_concept"]))}


def _dimensions(context: Any) -> dict[str, str]:
    from lxml import etree
    output = {}
    for qname, value in context.qnameDims.items():
        if value.isExplicit:
            output[str(qname)] = str(value.memberQname)
        else:
            output[str(qname)] = etree.tostring(value.typedMember, encoding="unicode")
    # Non-dimensional segment/scenario content is not consolidated by default.
    for name in ("segNonDimValues", "scenNonDimValues"):
        values = getattr(context, name, [])
        if values:
            output[f"__{name}"] = "|".join(etree.tostring(v, encoding="unicode") for v in values)
    return output


def _unit(unit: Any) -> str:
    if unit is None:
        return ""
    numerator, denominator = unit.measures
    def label(qname: Any) -> str:
        return qname.localName if qname.namespaceURI == "http://www.xbrl.org/2003/iso4217" else str(qname)
    top = "*".join(sorted(label(q) for q in numerator))
    return top if not denominator else top + "/" + "*".join(sorted(label(q) for q in denominator))


def restore_taxonomy_cache(root: Path, cache_dir: Path) -> int:
    """Restore vendored standards to Arelle's URL cache without network access."""
    manifest = root / "data/manifests/taxonomy_sources.jsonl"
    count = 0
    for record in load_jsonl(manifest):
        target = (cache_dir / record["cache_relative_path"]).resolve()
        if not target.is_relative_to(cache_dir.resolve()):
            raise ValueError("Taxonomy cache path escapes configured directory")
        data = read_source(root, record)
        if not target.exists() or sha256(target.read_bytes()) != record["sha256"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        count += 1
    return count


def snapshot_taxonomy_cache(root: Path, cache_dir: Path) -> int:
    """Archive standard taxonomy bytes downloaded by Arelle for offline replay."""
    from filingtime.ingest import append_jsonl
    manifest = root / "data/manifests/taxonomy_sources.jsonl"
    known = {r["cache_relative_path"]: r for r in load_jsonl(manifest)}
    for file in sorted(cache_dir.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in {".xsd", ".xml"}:
            continue
        relative = file.relative_to(cache_dir).as_posix()
        data = file.read_bytes()
        if relative in known:
            if sha256(data) != known[relative]["sha256"]:
                raise ValueError(f"Previously snapshotted taxonomy changed: {relative}")
            continue
        compressed = gzip.compress(data, compresslevel=9, mtime=0)
        destination = root / "data/raw/taxonomy" / (relative + ".gz")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(compressed)
        scheme, remainder = relative.split("/", 1)
        record = {"url": scheme + "://" + remainder, "local_path": destination.relative_to(root).as_posix(), "cache_relative_path": relative, "role": "standard_taxonomy_dependency", "retrieved_at": utc_now(), "retrieved_at_note": "Time archived from Arelle cache; exact HTTP retrieval time not observed", "sha256": sha256(data), "compressed_sha256": sha256(compressed), "bytes": len(data), "compressed_bytes": len(compressed)}
        append_jsonl(manifest, record)
        known[relative] = record
    return len(known)


def parse_filing(root: Path, filing: dict[str, Any], work_dir: Path, allow_network: bool = False, validate: bool = True) -> tuple[list[RevenueFact], dict[str, Any]]:
    """Return raw candidates and extraction audit; no normalization is inferred."""
    root, work_dir = root.resolve(), work_dir.resolve()
    if filing.get("split") == "holdout":
        from filingtime.freeze import check_freeze
        if check_freeze(root)["status"] != "unchanged":
            raise ValueError("Holdout parsing requires unchanged frozen rules")
    if allow_network and "@" not in os.environ.get("SEC_USER_AGENT", ""):
        raise ValueError("Online parsing requires SEC_USER_AGENT with a real contact email")
    os.environ["XDG_CONFIG_HOME"] = str(work_dir / "arelle-config")
    from arelle import Cntlr
    from arelle.ModelFormulaObject import FormulaOptions
    import importlib.metadata

    folder = unpack_filing(root, filing, work_dir)
    entry = _entrypoint(folder, filing)
    cache_dir = work_dir / "arelle-cache"
    restore_taxonomy_cache(root, cache_dir)
    controller = Cntlr.Cntlr(logFileName="logToBuffer", disable_persistent_config=True)
    controller.modelManager.formulaOptions = FormulaOptions()
    controller.webCache.cacheDir = str(cache_dir)
    controller.webCache.workOffline = not allow_network
    controller.webCache.httpsRedirect = True
    controller.webCache.timeout = 30
    controller.webCache.maxAgeSeconds = float("inf")
    controller.webCache.httpUserAgent = os.environ.get("SEC_USER_AGENT", "FilingTime offline research")
    # The pip distribution excludes EDGAR transforms. Activate the unmodified,
    # commit-pinned official transformation module; this is not full EFM validation.
    from filingtime._vendor.sec_transform import loadSECtransforms
    controller.modelManager.loadCustomTransforms()
    loadSECtransforms(controller.modelManager.customTransforms)
    # Archive URLs remain the canonical source identity, even when parsing local
    # byte-identical files. Each source document has its own hash and URL.
    sources_by_name = {Path(f["local_path"]).stem: f for f in filing["files"]}
    audit: dict[str, Any] = {"accession": filing["accession"], "cik": filing["cik"], "ticker": filing["ticker"], "split": filing["split"], "report_date": filing["report_date"], "parsed_at": utc_now(), "arelle_version": importlib.metadata.version("arelle-release"), "entrypoint": entry.name, "network_allowed": allow_network, "validation_requested": validate, "fiscal_year_focus": None, "document_period_end": None, "candidate_count": 0, "notes": ["Candidate extraction is not accounting or human validation."]}
    audit["extractor_sha256"] = sha256(Path(__file__).read_bytes())
    model = None
    try:
        model = controller.modelManager.load(str(entry))
        if model is None or model.modelDocument is None:
            raise ValueError(f"Arelle could not load {entry}")
        if validate and filing.get("is_xbrl"):
            controller.modelManager.validate()
        errors = [str(code) for code in model.errors]
        audit["arelle_errors"] = errors
        audit["arelle_log"] = controller.logHandler.getText()
        fatal = [e for e in errors if e in {"IOerror", "FileNotLoadable", "schemaImportMissing"} or "schemaImportMissing" in e or e.startswith("exception:")]
        if fatal:
            raise ValueError(f"Incomplete Arelle load: {fatal[:5]}")
        roles = _role_index(model)
        audit.update(_accounting_relationships(model))
        candidates = []
        for fact in sorted(model.factsInInstance, key=lambda item: item.objectIndex):
            qname = fact.qname
            if qname is None:
                continue
            if qname.localName == "DocumentFiscalYearFocus":
                audit["fiscal_year_focus"] = str(fact.value)
            elif qname.localName == "DocumentPeriodEndDate":
                audit["document_period_end"] = str(fact.value)
            if not fact.isNumeric:
                continue
            context = fact.context
            if context is None or not context.isStartEndPeriod:
                continue
            label = fact.concept.label(lang="en-US") if fact.concept is not None else ""
            if not REVENUE_PATTERN.search(qname.localName + " " + (label or "")):
                continue
            period_start = context.startDatetime.date().isoformat()
            period_end = (context.endDatetime - timedelta(days=1)).date().isoformat()
            # Preserve all duration revenue candidates, including nonannual
            # contexts, so normalization can audit explicit exclusions.
            value = None
            reason = "unreviewed_raw_candidate"
            try:
                if not fact.isNil:
                    raw = getattr(fact, "xValue", None)
                    if raw is None:
                        raw = fact.value
                    number = Decimal(str(raw))
                    if not number.is_finite():
                        raise InvalidOperation
                    value = format(number, "f")
            except (InvalidOperation, ValueError, TypeError):
                reason = "unparseable_numeric_candidate"
            from arelle.XmlValidateConst import VALID
            if getattr(fact, "xValid", 0) < VALID:
                reason = "invalid_xbrl_numeric_fact"
                value = None
            origin_name = Path(fact.modelDocument.filepath).name
            if origin_name not in sources_by_name:
                raise ValueError(f"Fact origin is not in the verified source manifest: {origin_name}")
            origin = sources_by_name[origin_name]
            entity_scheme, entity_identifier = context.entityIdentifier
            if entity_scheme.rstrip("/").lower() not in {"http://www.sec.gov/cik", "https://www.sec.gov/cik"} or not entity_identifier.isdigit() or entity_identifier.zfill(10) != filing["cik"].zfill(10):
                audit.setdefault("context_identity_issues", []).append({"context_id": fact.contextID, "scheme": entity_scheme, "identifier": entity_identifier, "expected_cik": filing["cik"]})
                reason = "context_entity_mismatch"
                value = None
            fact_id = fact.id or f"line-{fact.sourceline}-object-{fact.objectIndex}"
            anchor = "#" + fact.id if fact.id else f"line:{fact.sourceline};context:{fact.contextID};concept:{qname}"
            candidates.append(RevenueFact(cik=filing["cik"], accession=filing["accession"], form=filing["form"], period_start=period_start, period_end=period_end, value=value, unit=_unit(fact.unit), concept=str(qname), concept_namespace=qname.namespaceURI, context_id=fact.contextID or "", dimensions=_dimensions(context), accepted_at=filing["accepted_at"], available_at=filing["available_at"], retrieved_at=filing["retrieved_at"], source_url=origin["url"], source_sha256=origin["sha256"], fact_id=fact_id, evidence_anchor=anchor, filing_path=origin["local_path"], decimals=str(fact.decimals or ""), label=label or "", statement_role="\n".join(roles.get(fact.concept, [])), status="ambiguous", reason=reason))
        audit["candidate_count"] = len(candidates)
        audit["total_xbrl_fact_count"] = len(model.factsInInstance)
        audit["status"] = "parsed" if candidates else "no_revenue_candidates"
        if allow_network:
            audit["snapshotted_taxonomy_files"] = snapshot_taxonomy_cache(root, cache_dir)
        return candidates, audit
    finally:
        if model is not None:
            model.close()
        controller.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    parser.add_argument("--tickers")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-holdout", action="store_true", help="Explicitly open held-out financial values after rule freeze")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-validate", action="store_true")
    parser.add_argument("--reparse", action="store_true", help="Regenerate derived candidates and validation logs from unchanged source bytes")
    args = parser.parse_args()
    if args.split == "holdout" and not args.allow_holdout:
        parser.error("Holdout parsing requires frozen rules and explicit --allow-holdout")
    if args.split == "holdout":
        from filingtime.freeze import check_freeze
        if check_freeze(args.root)["status"] != "unchanged":
            parser.error("Holdout parsing requires unchanged frozen rules")
    filings = [r for r in load_jsonl(args.root / "data/manifests/filings.jsonl") if r["split"] == args.split]
    if args.tickers:
        filings = [r for r in filings if r["ticker"] in set(args.tickers.upper().split(","))]
    if args.limit:
        filings = filings[:args.limit]
    outdir = args.root / "data/manifests/candidates"
    auditdir = args.root / "data/manifests/parsed"
    outdir.mkdir(parents=True, exist_ok=True)
    auditdir.mkdir(parents=True, exist_ok=True)
    for filing in filings:
        output = outdir / (filing["accession"] + ".jsonl")
        auditfile = auditdir / (filing["accession"] + ".json")
        if output.exists() and auditfile.exists() and not args.reparse:
            previous_audit = json.loads(auditfile.read_text(encoding="utf-8"))
            if previous_audit.get("extractor_sha256") == sha256(Path(__file__).read_bytes()) and previous_audit.get("validation_requested") == (not args.no_validate):
                continue
        print(f"parse {filing['ticker']} {filing['accession']}", flush=True)
        candidates, audit = parse_filing(args.root, filing, args.work_dir, args.allow_network, not args.no_validate)
        output.write_text("".join(json.dumps(f.to_dict(), sort_keys=True, ensure_ascii=False) + "\n" for f in candidates), encoding="utf-8")
        auditfile.write_text(json.dumps(audit, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"parsed {len(candidates)} candidates; FY={audit['fiscal_year_focus']}; period={audit['document_period_end']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
