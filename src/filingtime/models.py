"""Evidence-preserving types for annual consolidated revenue observations.

Synthetic records and unreviewed mappings use the same types as real observations.
``status='accepted'`` means the normalization rule admitted a fact; it does not
mean an independent human has reviewed the company's accounting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Literal

Mode = Literal["pit", "latest", "period_end"]
VALID_MODES = frozenset(("pit", "latest", "period_end"))
UTC = timezone.utc


def utc_datetime(value: str | datetime | date) -> datetime:
    """Parse an aware instant; bare dates mean 23:59:59.999999 UTC.

    Naive *datetimes* are rejected rather than silently assigning a timezone.
    A bare date is deliberately a calendar-day query, not an SEC timestamp.
    """
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.max.time(), tzinfo=UTC)
    else:
        value = str(value).strip()
        if len(value) == 10:
            return utc_datetime(date.fromisoformat(value))
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timestamps must include an explicit timezone")
    return result.astimezone(UTC)


def iso_utc(value: str | datetime | date) -> str:
    return utc_datetime(value).isoformat().replace("+00:00", "Z")


def instant_utc(value: str | datetime) -> str:
    """Normalize a recorded instant; unlike queries, dates are not sufficient."""
    if (isinstance(value, date) and not isinstance(value, datetime)) or (
        isinstance(value, str) and len(value.strip()) == 10
    ):
        raise ValueError("Recorded timestamps require an aware instant, not a bare date")
    return iso_utc(value)


def iso_date(value: str | date) -> str:
    if isinstance(value, datetime):
        raise ValueError("A financial period must be a date, not a timestamp")
    return (value if isinstance(value, date) else date.fromisoformat(value)).isoformat()


def decimal_text(value: str | Decimal | int) -> str:
    if isinstance(value, (float, bool)):
        raise TypeError("Financial values must be decimal strings, Decimal, or int")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc
    if not number.is_finite():
        raise ValueError("Financial values must be finite")
    return format(number, "f")


def canonical_dimensions(value: str | dict[str, Any] | None) -> str:
    if value is None:
        value = {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("Dimensions must be a JSON object, not a list or scalar")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class RevenueFact:
    cik: str
    accession: str
    form: str
    period_start: str
    period_end: str
    value: str | None
    unit: str
    concept: str
    context_id: str
    accepted_at: str
    source_url: str
    source_sha256: str
    fact_id: str
    available_at: str = ""
    retrieved_at: str = ""
    dimensions: str = "{}"
    basis_id: str = ""
    status: str = "ambiguous"
    reason: str = "normalization_not_established"
    evidence_anchor: str = ""
    filing_path: str = ""
    decimals: str = ""
    label: str = ""
    statement_role: str = ""
    mapping_version: str = ""
    reference_id: str = ""
    concept_namespace: str = ""

    def __post_init__(self) -> None:
        cik = str(self.cik).strip()
        if not cik.isdigit():
            raise ValueError("CIK must contain only digits")
        object.__setattr__(self, "cik", cik.zfill(10))
        object.__setattr__(self, "period_start", iso_date(self.period_start))
        object.__setattr__(self, "period_end", iso_date(self.period_end))
        if self.period_end < self.period_start:
            raise ValueError("Financial period ends before it starts")
        object.__setattr__(self, "accepted_at", instant_utc(self.accepted_at))
        accepted = utc_datetime(self.accepted_at)
        expected_available = accepted + timedelta(hours=24)
        available = expected_available if not self.available_at else utc_datetime(instant_utc(self.available_at))
        if available != expected_available:
            raise ValueError("Availability must equal SEC acceptance plus exactly 24 elapsed hours")
        object.__setattr__(self, "available_at", iso_utc(available))
        if self.retrieved_at:
            object.__setattr__(self, "retrieved_at", instant_utc(self.retrieved_at))
        object.__setattr__(self, "dimensions", canonical_dimensions(self.dimensions))
        if self.value is not None:
            object.__setattr__(self, "value", decimal_text(self.value))
        if self.status not in {"accepted", "ambiguous", "rejected"}:
            raise ValueError("Fact status must be accepted, ambiguous, or rejected")
        if self.status == "accepted" and (not self.basis_id or self.value is None):
            raise ValueError("Accepted facts require an explicit basis_id and a value")
        if self.status == "accepted" and self.reason == "normalization_not_established":
            object.__setattr__(self, "reason", "admitted_by_explicit_mapping")
        if not self.accession or not self.fact_id or not self.source_url:
            raise ValueError("A fact needs accession, fact_id, and source_url provenance")
        if len(self.source_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in self.source_sha256):
            raise ValueError("source_sha256 must be a 64-character SHA-256 hex digest")
        object.__setattr__(self, "source_sha256", self.source_sha256.lower())

    @property
    def number(self) -> Decimal | None:
        return Decimal(self.value) if self.value is not None else None

    @property
    def duration_days(self) -> int:
        return (date.fromisoformat(self.period_end) - date.fromisoformat(self.period_start)).days + 1

    @property
    def is_annual(self) -> bool:
        return 350 <= self.duration_days <= 380

    @property
    def is_consolidated(self) -> bool:
        return self.dimensions == "{}"

    @property
    def identity(self) -> str:
        """Stable identity independent of the value, to detect silent replacement."""
        key = [self.cik, self.accession, self.source_url, self.fact_id]
        return hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "RevenueFact":
        names = {field.name for field in fields(cls)}
        extra = set(record) - names
        if extra:
            raise ValueError(f"Unknown RevenueFact fields: {sorted(extra)}")
        return cls(**record)


@dataclass(frozen=True, slots=True)
class QueryResult:
    status: str
    reason: str
    cik: str
    period_end: str
    as_of: str
    mode: str
    fact: RevenueFact | None = None
    evidence: tuple[RevenueFact, ...] = ()
    effective_at: str | None = None
    candidate_count: int = 0
    diagnostics: tuple[str, ...] = ()

    @property
    def value(self) -> str | None:
        return self.fact.value if self.fact else None

    @property
    def number(self) -> Decimal | None:
        return self.fact.number if self.fact else None

    @property
    def uses_future_information(self) -> bool:
        return bool(self.fact and utc_datetime(self.fact.available_at) > utc_datetime(self.as_of))

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["value"] = self.value
        result["uses_future_information"] = self.uses_future_information
        return result


@dataclass(frozen=True, slots=True)
class GrowthResult:
    status: str
    reason: str
    current: QueryResult
    previous: RevenueFact | None = None
    growth: str | None = None
    evidence: tuple[RevenueFact, ...] = ()

    @property
    def number(self) -> Decimal | None:
        return Decimal(self.growth) if self.growth is not None else None

    @property
    def uses_future_information(self) -> bool:
        return self.current.uses_future_information or bool(
            self.previous and utc_datetime(self.previous.available_at) > utc_datetime(self.current.as_of)
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["current"] = self.current.to_dict()
        result["uses_future_information"] = self.uses_future_information
        return result


def load_facts(path: str | Path) -> list[RevenueFact]:
    """Load a JSON array or JSONL; fail loudly on malformed/unknown records."""
    source = Path(path)
    text = source.read_text(encoding="utf-8-sig")
    rows = json.loads(text) if text.lstrip().startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
    return [RevenueFact.from_dict(row) for row in rows]


def save_facts(path: str | Path, facts: Iterable[RevenueFact]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(facts, key=lambda f: (f.cik, f.period_end, f.available_at, f.accession, f.fact_id))
    target.write_text("".join(json.dumps(f.to_dict(), sort_keys=True, ensure_ascii=False) + "\n" for f in records), encoding="utf-8")
