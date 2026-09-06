from app.services.entity_resolution import EntityResolutionService, normalize_text
from app.services.knowledge_graph import KnowledgeGraphService


CASE = "case_test-001"


def test_normalization_and_deterministic_matching(make_record) -> None:
    assert normalize_text("  Avery-Rowan ") == "averyrowan"
    records = [
        make_record("per_phase3-001", "person", {"entity_id": "per_phase3-001", "display_name": "Avery Rowan"}),
        make_record("per_phase3-002", "person", {"entity_id": "per_phase3-002", "display_name": " avery-rowan "}),
    ]

    result = EntityResolutionService().resolve(CASE, records)

    assert len(result.entities) == 1
    entity = result.entities[0]
    assert entity.match_status == "exact_match"
    assert entity.source_entity_ids == ["per_phase3-001", "per_phase3-002"]
    assert entity.match_confidence == 1.0
    # Both contributing records remain attributable to the merged identity.
    assert len(entity.provenance) == 2


def test_canonical_id_does_not_depend_on_record_order(make_record) -> None:
    first = make_record("per_order-001", "person", {"entity_id": "per_order-001", "display_name": "Avery Rowan"})
    second = make_record("per_order-002", "person", {"entity_id": "per_order-002", "display_name": "Avery Rowan"})

    forwards = EntityResolutionService().resolve(CASE, [first, second])
    backwards = EntityResolutionService().resolve(CASE, [second, first])

    assert forwards.entities[0].canonical_id == backwards.entities[0].canonical_id


def test_non_matching_entities_remain_separate(make_record) -> None:
    records = [
        make_record("phn_phase3-001", "phone", {"entity_id": "phn_phase3-001", "number": "+15550101"}),
        make_record("phn_phase3-002", "phone", {"entity_id": "phn_phase3-002", "number": "+15559902"}),
    ]

    result = EntityResolutionService().resolve(CASE, records)

    assert len(result.entities) == 2
    assert all(entity.match_status == "canonical" for entity in result.entities)


def test_ambiguous_fuzzy_match_is_flagged_not_merged(make_record) -> None:
    records = [
        make_record("org_phase3-001", "organization", {"entity_id": "org_phase3-001", "name": "Northstar Demo Cooperative"}),
        make_record("org_phase3-002", "organization", {"entity_id": "org_phase3-002", "name": "Northstar Demo Cooperatives"}),
    ]

    result = EntityResolutionService().resolve(CASE, records)

    assert len(result.entities) == 2
    flagged = result.entities[1]
    assert flagged.match_status == "candidate_review"
    assert flagged.review_candidates == [result.entities[0].canonical_id]
    assert 0.88 <= flagged.match_confidence < 1
    assert "org_phase3-002" in result.unresolved_record_ids


def test_graph_nodes_edges_and_provenance_are_preserved(make_record) -> None:
    records = [
        make_record("per_phase3-001", "person", {"entity_id": "per_phase3-001", "display_name": "Avery Rowan"}),
        make_record("phn_phase3-001", "phone", {"entity_id": "phn_phase3-001", "number": "+15550101"}),
        make_record(
            "com_phase3-001",
            "communication",
            {
                "record_id": "com_phase3-001",
                "from_entity_id": "per_phase3-001",
                "to_entity_id": "phn_phase3-001",
                "occurred_at": "2026-01-01T00:00:00Z",
                "channel": "call",
            },
        ),
    ]

    graph = KnowledgeGraphService().build("graph_phase3-001", CASE, records)

    assert {node.entity_type for node in graph.nodes} == {"person", "phone"}
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    # A communication is expressed in the canonical relationship vocabulary.
    assert edge.relationship_type == "contacted"
    assert edge.source_record_ids == ["com_phase3-001"]
    assert edge.provenance[0].source_record_id == "src_test-001"
    assert graph.nodes[0].provenance[0].source_record_id == "src_test-001"
    assert graph.rejected_edges == []


def test_incident_records_become_nodes(make_record) -> None:
    records = [
        make_record("inc_phase3-001", "incident", {"entity_id": "inc_phase3-001", "summary": "Fictional demo event"}),
    ]

    graph = KnowledgeGraphService().build("graph_phase3-002", CASE, records)

    assert [node.entity_type for node in graph.nodes] == ["incident"]


def test_evidence_source_records_do_not_become_nodes(make_record) -> None:
    records = [
        make_record(
            "src_phase3-009",
            "evidence_source",
            {
                "record_id": "src_phase3-009",
                "source_type": "synthetic_report",
                "title": "Demo source",
                "collected_at": "2026-01-01T00:00:00Z",
                "reliability": "high",
                "content": "Fictional content.",
            },
        ),
    ]

    graph = KnowledgeGraphService().build("graph_phase3-003", CASE, records)

    assert graph.nodes == []
