from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import KnowledgeRecord, KnowledgeSource
from .registry import KnowledgeRegistry, SourceRegistry


def _read_json(path: str | Path) -> Any:
    target = Path(path)
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"knowledge source file not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in knowledge source file: {target}") from exc


def _rows(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get(key), list):
        rows = payload[key]
    else:
        raise ValueError(f"expected a JSON list or object containing '{key}'")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("all knowledge/source entries must be JSON objects")
    return rows


def load_sources(path: str | Path) -> list[KnowledgeSource]:
    return [
        KnowledgeSource.from_dict(row)
        for row in _rows(_read_json(path), "sources")
    ]


def load_records(
    path: str | Path,
    *,
    source_registry: SourceRegistry | None = None,
) -> list[KnowledgeRecord]:
    records: list[KnowledgeRecord] = []
    for row in _rows(_read_json(path), "records"):
        data = dict(row)
        source_id = str(data.get("source_id") or "")
        if source_registry is not None and source_id:
            source = source_registry.get(source_id)
            if source is None:
                raise ValueError(f"knowledge record references unknown source: {source_id}")
            if not data.get("source_type"):
                data["source_type"] = source.source_type
            if data.get("authority_level") is None:
                data["authority_level"] = source.authority_level
        records.append(KnowledgeRecord.from_dict(data))
    return records


def ingest(
    *,
    source_file: str | Path,
    record_file: str | Path | None = None,
    source_registry: SourceRegistry,
    knowledge_registry: KnowledgeRegistry | None = None,
    replace_existing: bool = False,
) -> tuple[int, int]:
    sources = load_sources(source_file)
    source_count = 0
    for source in sources:
        source_registry.add(source, replace_existing=replace_existing)
        source_count += 1

    record_count = 0
    if record_file is not None:
        if knowledge_registry is None:
            raise ValueError("knowledge_registry is required when record_file is provided")
        records = load_records(record_file, source_registry=source_registry)
        record_count = knowledge_registry.add_many(
            records,
            replace_existing=replace_existing,
        )
    return source_count, record_count
