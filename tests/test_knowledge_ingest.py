from pathlib import Path

from wq_evo.knowledge import KnowledgeRegistry, SourceRegistry
from wq_evo.knowledge.ingest import ingest, load_records, load_sources


ROOT = Path(__file__).resolve().parents[1]


def test_seed_sources_and_records_are_loadable(tmp_path: Path):
    source_file = ROOT / "knowledge" / "sources" / "worldquant_official.json"
    record_file = ROOT / "knowledge" / "brain" / "official_records.json"

    sources = load_sources(source_file)
    assert len(sources) >= 6
    official = [source for source in sources if source.source_type in {"worldquant_official", "brain_learn", "webinar"}]
    community = [source for source in sources if source.source_type == "community"]
    assert official and all(source.authority_level == 2 for source in official)
    assert community and all(source.authority_level == 4 for source in community)

    source_registry = SourceRegistry(tmp_path / "sources.json")
    knowledge_registry = KnowledgeRegistry(tmp_path / "knowledge.json")

    source_count, record_count = ingest(
        source_file=source_file,
        record_file=record_file,
        source_registry=source_registry,
        knowledge_registry=knowledge_registry,
    )
    assert source_count == len(sources)
    assert record_count >= 8
    assert knowledge_registry.search("research area")
    assert knowledge_registry.list_by_source("wq-eric-gitau-spotlight")
