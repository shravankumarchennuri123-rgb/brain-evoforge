from pathlib import Path

import pytest

from wq_evo.knowledge import (
    KnowledgeRecord,
    KnowledgeRegistry,
    KnowledgeSource,
    SourceRegistry,
)


def test_knowledge_record_id_is_deterministic():
    a = KnowledgeRecord(
        title="Alpha definition",
        source_id="wq-brain",
        topic="platform",
        claim="An alpha is a mathematical model seeking to predict future price movements.",
    )
    b = KnowledgeRecord(
        title="Alpha definition",
        source_id="wq-brain",
        topic="platform",
        claim="An alpha is a mathematical model seeking to predict future price movements.",
    )
    assert a.record_id == b.record_id


def test_registries_persist_and_search(tmp_path: Path):
    source_path = tmp_path / "sources.json"
    knowledge_path = tmp_path / "knowledge.json"

    sources = SourceRegistry(source_path)
    source = KnowledgeSource(
        source_id="wq-brain",
        title="WorldQuant BRAIN",
        source_type="worldquant_official",
        authority_level=2,
        url="https://www.worldquant.com/brain/",
        topics=("platform", "alpha"),
    )
    sources.add(source)

    reloaded_sources = SourceRegistry(source_path)
    assert reloaded_sources.get("wq-brain") == source
    assert reloaded_sources.search("platform")[0].source_id == "wq-brain"

    knowledge = KnowledgeRegistry(knowledge_path)
    record = KnowledgeRecord(
        title="Alpha definition",
        source_id="wq-brain",
        source_type="worldquant_official",
        authority_level=2,
        topic="platform",
        claim="Alphas are mathematical models that seek to predict future price movements.",
        tags=("alpha", "definition"),
    )
    knowledge.add(record)

    reloaded = KnowledgeRegistry(knowledge_path)
    assert reloaded.get(record.record_id) == record
    assert reloaded.list_by_topic("platform") == [record]
    assert reloaded.list_by_source("wq-brain") == [record]
    assert reloaded.search("future price")[0] == record


def test_duplicate_add_requires_explicit_replace(tmp_path: Path):
    path = tmp_path / "knowledge.json"
    registry = KnowledgeRegistry(path)
    record = KnowledgeRecord(
        title="Test",
        source_id="source",
        topic="test",
        claim="A claim.",
    )
    registry.add(record)
    with pytest.raises(ValueError):
        registry.add(record)
    replacement = KnowledgeRecord(
        title="Test",
        source_id="source",
        topic="test",
        claim="A changed claim.",
        record_id=record.record_id,
    )
    registry.add(replacement, replace_existing=True)
    assert registry.get(record.record_id).claim == "A changed claim."


def test_invalid_confidence_is_rejected():
    with pytest.raises(ValueError):
        KnowledgeRecord(
            title="Test",
            source_id="source",
            topic="test",
            claim="A claim.",
            confidence=1.1,
        )


def test_live_verification_is_explicit(tmp_path: Path):
    registry = KnowledgeRegistry(tmp_path / "knowledge.json")
    record = KnowledgeRecord(
        title="Test",
        source_id="source",
        topic="test",
        claim="A claim.",
    )
    registry.add(record)
    updated = registry.mark_live_verified(record.record_id, verified_at="2026-09-19T00:00:00Z")
    assert updated.live_verified is True
    assert updated.verified_at == "2026-09-19T00:00:00Z"
