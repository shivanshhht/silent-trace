from datetime import datetime, timezone

from app.schemas.investigation import IngestedRecord
from app.services.entity_resolution import EntityResolutionService, normalize_text
from app.services.knowledge_graph import KnowledgeGraphService


def ingested(record_id: str, record_type: str, data: dict) -> IngestedRecord:
    return IngestedRecord(
        record_id=record_id,
        record_type=record_type,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data=data,
        provenance=["src_phase3-001"],
    )


def test_normalization_and_deterministic_matching() -> None:
    assert normalize_text("  Avery-Röwan ") == "averyrowan"
    records = [
        ingested("per_phase3-001", "person", {"entity_id": "per_phase3-001", "display_name": "Avery Rowan"}),
        ingested("per_phase3-002", "person", {"entity_id": "per_phase3-002", "display_name": " avery-rowan "}),
    ]
    result = EntityResolutionService().resolve(records)
    assert len(result.entities) == 1
    assert result.entities[0].match_status == "exact_match"
    assert result.entities[0].source_entity_ids == ["per_phase3-001", "per_phase3-002"]
    assert result.entities[0].match_confidence == 1.0


def test_non_matching_entities_remain_separate() -> None:
    records = [
        ingested("phn_phase3-001", "phone", {"entity_id": "phn_phase3-001", "number": "+15550101"}),
        ingested("phn_phase3-002", "phone", {"entity_id": "phn_phase3-002", "number": "+15550202"}),
    ]
    result = EntityResolutionService().resolve(records)
    assert len(result.entities) == 2
    assert all(entity.match_status == "canonical" for entity in result.entities)


def test_ambiguous_fuzzy_match_is_flagged_not_merged() -> None:
    records = [
        ingested("org_phase3-001", "organization", {"entity_id": "org_phase3-001", "name": "Northstar Demo Cooperative", "organization_type": "cooperative"}),
        ingested("org_phase3-002", "organization", {"entity_id": "org_phase3-002", "name": "Northstar Demo Cooperatives", "organization_type": "cooperative"}),
    ]
    result = EntityResolutionService().resolve(records)
    assert len(result.entities) == 2
    assert result.entities[1].match_status == "candidate_review"
    assert result.entities[1].review_candidates == ["org_phase3-001"]
    assert 0.88 <= result.entities[1].match_confidence < 1


def test_graph_nodes_edges_and_provenance_are_preserved() -> None:
    records = [
        ingested("per_phase3-001", "person", {"entity_id": "per_phase3-001", "display_name": "Avery Rowan"}),
        ingested("phn_phase3-001", "phone", {"entity_id": "phn_phase3-001", "number": "+15550101"}),
        ingested("com_phase3-001", "communication", {"record_id": "com_phase3-001", "from_entity_id": "per_phase3-001", "to_entity_id": "phn_phase3-001", "occurred_at": "2026-01-01T00:00:00Z", "channel": "call"}),
    ]
    graph = KnowledgeGraphService().build("graph_phase3-001", records)
    assert {node.node_id for node in graph.nodes} == {"per_phase3-001", "phn_phase3-001"}
    assert len(graph.edges) == 1
    assert graph.edges[0].relationship_type == "communication"
    assert graph.edges[0].source_record_id == "src_phase3-001"
    assert graph.edges[0].provenance[0].record_id == "com_phase3-001"
    assert graph.nodes[0].provenance[0].source_record_id == "src_phase3-001"
