from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from .models import KnowledgeRecord, KnowledgeSource


SCHEMA_VERSION = 1


class _JsonRegistry:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._rows: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid knowledge registry JSON: {self.path}") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise ValueError(f"invalid knowledge registry schema: {self.path}")

        for row in payload["records"]:
            if not isinstance(row, dict):
                raise ValueError("registry records must be JSON objects")
            key = str(row.get(self._id_key()) or "")
            if not key:
                raise ValueError(f"registry record missing {self._id_key()}")
            self._rows[key] = row

    def _id_key(self) -> str:
        raise NotImplementedError

    def _encode(self, row: Any) -> dict[str, Any]:
        raise NotImplementedError

    def _decode(self, row: dict[str, Any]) -> Any:
        raise NotImplementedError

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "records": list(self._rows.values()),
        }
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _iter(self) -> Iterable[Any]:
        for row in self._rows.values():
            yield self._decode(row)

    def _search_value(self, item: Any) -> str:
        raise NotImplementedError

    def get(self, item_id: str) -> Any | None:
        row = self._rows.get(str(item_id))
        return self._decode(row) if row else None

    def search(self, query: str) -> list[Any]:
        needle = str(query).strip().lower()
        if not needle:
            return list(self._iter())
        return [
            item for item in self._iter()
            if needle in self._search_value(item).lower()
        ]

    def export(self, path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "records": list(self._rows.values()),
        }
        if path is not None:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return payload


class SourceRegistry(_JsonRegistry):
    """Persistent registry of BRAIN/documentation/literature source metadata."""

    def _id_key(self) -> str:
        return "source_id"

    def _encode(self, row: KnowledgeSource) -> dict[str, Any]:
        return row.to_dict()

    def _decode(self, row: dict[str, Any]) -> KnowledgeSource:
        return KnowledgeSource.from_dict(row)

    def _search_value(self, item: KnowledgeSource) -> str:
        return " ".join([
            item.source_id,
            item.title,
            item.source_type,
            item.authority_name,
            item.url,
            *item.topics,
            item.notes,
        ])

    def add(self, source: KnowledgeSource, *, replace_existing: bool = False) -> KnowledgeSource:
        existing = self._rows.get(source.source_id)
        if existing is not None and not replace_existing:
            raise ValueError(f"source already exists: {source.source_id}")
        self._rows[source.source_id] = self._encode(source)
        self._save()
        return source

    def list_by_type(self, source_type: str) -> list[KnowledgeSource]:
        return [
            item for item in self._iter()
            if item.source_type == source_type
        ]

    def list_by_topic(self, topic: str) -> list[KnowledgeSource]:
        needle = str(topic).strip().lower()
        return [
            item for item in self._iter()
            if needle in {tag.lower() for tag in item.topics}
        ]


class KnowledgeRegistry(_JsonRegistry):
    """Persistent registry of atomic, source-backed research knowledge."""

    def _id_key(self) -> str:
        return "record_id"

    def _encode(self, row: KnowledgeRecord) -> dict[str, Any]:
        return row.to_dict()

    def _decode(self, row: dict[str, Any]) -> KnowledgeRecord:
        return KnowledgeRecord.from_dict(row)

    def _search_value(self, item: KnowledgeRecord) -> str:
        return " ".join([
            item.record_id,
            item.title,
            item.source_id,
            item.source_type,
            item.topic,
            item.claim,
            item.details,
            *item.tags,
            item.source_locator,
            item.notes,
        ])

    def add(self, record: KnowledgeRecord, *, replace_existing: bool = False) -> KnowledgeRecord:
        existing = self._rows.get(record.record_id)
        if existing is not None and not replace_existing:
            raise ValueError(f"knowledge record already exists: {record.record_id}")
        self._rows[record.record_id] = self._encode(record)
        self._save()
        return record

    def add_many(
        self,
        records: Iterable[KnowledgeRecord],
        *,
        replace_existing: bool = False,
    ) -> int:
        staged = list(records)
        for record in staged:
            existing = self._rows.get(record.record_id)
            if existing is not None and not replace_existing:
                raise ValueError(f"knowledge record already exists: {record.record_id}")

        for record in staged:
            self._rows[record.record_id] = self._encode(record)
        if staged:
            self._save()
        return len(staged)

    def list_by_topic(self, topic: str) -> list[KnowledgeRecord]:
        needle = str(topic).strip().lower()
        return [
            item for item in self._iter()
            if item.topic.strip().lower() == needle
        ]

    def list_by_source(self, source_id: str) -> list[KnowledgeRecord]:
        return [
            item for item in self._iter()
            if item.source_id == str(source_id)
        ]

    def mark_live_verified(
        self,
        record_id: str,
        *,
        verified_at: str,
        notes: str | None = None,
    ) -> KnowledgeRecord:
        record = self.get(record_id)
        if record is None:
            raise KeyError(f"knowledge record not found: {record_id}")
        updated = replace(
            record,
            live_verified=True,
            verified_at=verified_at,
            notes=record.notes if notes is None else notes,
        )
        self._rows[record_id] = self._encode(updated)
        self._save()
        return updated
