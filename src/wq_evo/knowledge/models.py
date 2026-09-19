from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Any, Mapping


AUTHORITY_LEVELS = {
    "live_brain": 1,
    "worldquant_official": 2,
    "academic": 3,
    "community": 4,
    "unverified": 5,
    "llm_generated": 6,
}

SOURCE_TYPES = {
    "live_brain",
    "worldquant_official",
    "brain_learn",
    "webinar",
    "academic",
    "community",
    "unverified",
    "llm_generated",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(*parts: str, prefix: str) -> str:
    payload = "\x1f".join(part.strip() for part in parts)
    return f"{prefix}-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]}"


def _clean_tags(tags: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(tag).strip() for tag in tags if str(tag).strip()}))


@dataclass(frozen=True)
class KnowledgeSource:
    source_id: str
    title: str
    source_type: str
    authority_level: int
    url: str = ""
    published_date: str | None = None
    accessed_at: str = field(default_factory=utc_now_iso)
    topics: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unsupported source_type: {self.source_type}")
        if self.authority_level not in AUTHORITY_LEVELS.values():
            raise ValueError(f"unsupported authority_level: {self.authority_level}")
        object.__setattr__(self, "topics", _clean_tags(self.topics))

    @property
    def authority_name(self) -> str:
        for name, level in AUTHORITY_LEVELS.items():
            if level == self.authority_level:
                return name
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type,
            "authority_level": self.authority_level,
            "authority_name": self.authority_name,
            "url": self.url,
            "published_date": self.published_date,
            "accessed_at": self.accessed_at,
            "topics": list(self.topics),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> "KnowledgeSource":
        return cls(
            source_id=str(row.get("source_id") or ""),
            title=str(row.get("title") or ""),
            source_type=str(row.get("source_type") or ""),
            authority_level=int(row.get("authority_level") or 0),
            url=str(row.get("url") or ""),
            published_date=row.get("published_date"),
            accessed_at=str(row.get("accessed_at") or utc_now_iso()),
            topics=tuple(row.get("topics") or ()),
            notes=str(row.get("notes") or ""),
        )


@dataclass(frozen=True)
class KnowledgeRecord:
    title: str
    source_id: str
    topic: str
    claim: str
    details: str = ""
    record_id: str = ""
    source_type: str = ""
    authority_level: int | None = None
    confidence: float = 1.0
    tags: tuple[str, ...] = ()
    source_locator: str = ""
    extracted_at: str = field(default_factory=utc_now_iso)
    verified_at: str | None = None
    live_verified: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not self.topic.strip():
            raise ValueError("topic must not be empty")
        if not self.claim.strip():
            raise ValueError("claim must not be empty")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.authority_level is not None and self.authority_level not in AUTHORITY_LEVELS.values():
            raise ValueError(f"unsupported authority_level: {self.authority_level}")

        record_id = self.record_id.strip() or stable_id(
            self.source_id,
            self.topic,
            self.title,
            self.claim,
            prefix="K",
        )
        object.__setattr__(self, "record_id", record_id)
        object.__setattr__(self, "tags", _clean_tags(self.tags))

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "title": self.title,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "authority_level": self.authority_level,
            "topic": self.topic,
            "claim": self.claim,
            "details": self.details,
            "confidence": float(self.confidence),
            "tags": list(self.tags),
            "source_locator": self.source_locator,
            "extracted_at": self.extracted_at,
            "verified_at": self.verified_at,
            "live_verified": self.live_verified,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> "KnowledgeRecord":
        return cls(
            record_id=str(row.get("record_id") or ""),
            title=str(row.get("title") or ""),
            source_id=str(row.get("source_id") or ""),
            source_type=str(row.get("source_type") or ""),
            authority_level=(
                int(row["authority_level"])
                if row.get("authority_level") is not None
                else None
            ),
            topic=str(row.get("topic") or ""),
            claim=str(row.get("claim") or ""),
            details=str(row.get("details") or ""),
            confidence=float(row.get("confidence", 1.0)),
            tags=tuple(row.get("tags") or ()),
            source_locator=str(row.get("source_locator") or ""),
            extracted_at=str(row.get("extracted_at") or utc_now_iso()),
            verified_at=row.get("verified_at"),
            live_verified=bool(row.get("live_verified", False)),
            notes=str(row.get("notes") or ""),
        )
