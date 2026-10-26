"""Append-only, content-addressed Parquet batches queried through DuckDB.

Re-importing an identical fact is idempotent. Changing any field of an existing
fact identity is an error: a new normalization policy needs a separate store.
The store is intended for a single writer, not concurrent ingestion processes.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import fields
from pathlib import Path
from typing import Iterable

from .models import RevenueFact


class FactStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    @property
    def parts(self) -> list[Path]:
        return sorted(self.directory.glob("facts-*.parquet"))

    def load(self) -> list[RevenueFact]:
        if not self.parts:
            return []
        import duckdb
        with duckdb.connect() as connection:
            cursor = connection.execute("SELECT DISTINCT * FROM read_parquet(?)", [[str(p) for p in self.parts]])
            names = [column[0] for column in cursor.description]
            rows = [RevenueFact.from_dict(dict(zip(names, row))) for row in cursor.fetchall()]
        return sorted(rows, key=lambda f: (f.cik, f.period_end, f.available_at, f.accession, f.fact_id))

    def append(self, facts: Iterable[RevenueFact]) -> Path | None:
        existing = {f.identity: f for f in self.load()}
        novel: dict[str, RevenueFact] = {}
        for fact in facts:
            previous = existing.get(fact.identity) or novel.get(fact.identity)
            if previous is not None and previous != fact:
                raise ValueError(f"Immutable fact replacement refused: {fact.identity}")
            if previous is None:
                novel[fact.identity] = fact
        if not novel:
            return None
        records = [novel[key].to_dict() for key in sorted(novel)]
        digest = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"facts-{digest}.parquet"
        if destination.exists():
            raise FileExistsError(f"Unexpected existing content-addressed batch: {destination}")
        temporary = destination.with_suffix(".parquet.tmp")
        import duckdb
        names = [field.name for field in fields(RevenueFact)]
        columns = ", ".join(f'"{name}" VARCHAR' for name in names)
        placeholders = ",".join("?" for _ in names)
        try:
            with duckdb.connect() as connection:
                connection.execute(f"CREATE TABLE new_facts ({columns})")
                connection.executemany(f"INSERT INTO new_facts VALUES ({placeholders})", [[record[name] for name in names] for record in records])
                connection.execute("COPY new_facts TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(temporary)])
            # No overwrite: exclusive-create destination before copying bytes.
            with destination.open("xb") as output, temporary.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def receipt(self) -> dict:
        return {
            "format": "filingtime-fact-store-v1",
            "fact_count": len(self.load()),
            "parts": [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in self.parts],
        }
