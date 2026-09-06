"""Regression tests for the defects Stage A was created to fix.

Each test names the behaviour it protects, not the implementation that provides
it, so the guarantees survive later refactoring.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.investigation import IngestedRecord, ProvenanceRecord
from app.schemas.nlp import ReportRequest
from app.services.entity_resolution import EntityResolutionService
from app.services.ingestion import PAYLOAD_MODELS
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.nlp_extraction import NLPExtractionService


client = TestClient(app)
WHEN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _report(case_id: str, source_record_id: str, text: str, report_id: str = "rpt_reg-001") -> ReportRequest:
    return ReportRequest(
        case_id=case_id,
        report_id=report_id,
        source_record_id=source_record_id,
        observed_at=WHEN,
        text=text,
    )


def _pipeline(report: ReportRequest):
    service = NLPExtractionService()
    extraction = service.extract(report)
    records, rejected = service.to_ingested_records(report, extraction)
    return extraction, records, rejected


# ---------------------------------------------------------------------------
# 1-3  Case scoping
# ---------------------------------------------------------------------------


def test_same_entity_in_two_cases_does_not_collide() -> None:
    """The quality gate: A contacted B in one case, A contacted C in another."""
    _, records_a, _ = _pipeline(_report("case_alpha-001", "src_alpha-001", "Avery Rowan contacted Blair Keene."))
    _, records_b, _ = _pipeline(_report("case_beta-001", "src_beta-001", "Avery Rowan contacted Casey Vance."))

    ids_a = {record.record_id for record in records_a}
    ids_b = {record.record_id for record in records_b}

    assert not (ids_a & ids_b), "records from unrelated investigations shared an identifier"

    graph_a = KnowledgeGraphService().build("graph_alpha-001", "case_alpha-001", records_a)
    graph_b = KnowledgeGraphService().build("graph_beta-001", "case_beta-001", records_b)

    names_a = {node.attributes.get("display_name") for node in graph_a.nodes if node.entity_type == "person"}
    names_b = {node.attributes.get("display_name") for node in graph_b.nodes if node.entity_type == "person"}
    assert names_a == {"Avery Rowan", "Blair Keene"}
    assert names_b == {"Avery Rowan", "Casey Vance"}
    assert not ({node.node_id for node in graph_a.nodes} & {node.node_id for node in graph_b.nodes})


def test_entity_identity_is_stable_within_a_case_and_distinct_across_cases() -> None:
    text = "Avery Rowan contacted Blair Keene."
    first = _pipeline(_report("case_alpha-001", "src_alpha-001", text))[0]
    again = _pipeline(_report("case_alpha-001", "src_alpha-002", text))[0]
    other = _pipeline(_report("case_beta-001", "src_beta-001", text))[0]

    def person_ids(extraction):
        return sorted(e.entity_id for e in extraction.extracted_entities if e.entity_type == "PERSON")

    assert person_ids(first) == person_ids(again), "identity must be stable within a case"
    assert person_ids(first) != person_ids(other), "identity must differ across cases"


def test_graph_cannot_be_built_from_records_spanning_cases() -> None:
    _, records_a, _ = _pipeline(_report("case_alpha-001", "src_alpha-001", "Avery Rowan contacted Blair Keene."))
    _, records_b, _ = _pipeline(_report("case_beta-001", "src_beta-001", "Avery Rowan contacted Casey Vance."))

    with pytest.raises(ValueError, match="case_beta-001"):
        KnowledgeGraphService().build("graph_mixed-001", "case_alpha-001", records_a + records_b)

    with pytest.raises(ValueError, match="do not belong to case"):
        EntityResolutionService().resolve("case_alpha-001", records_a + records_b)


def test_provenance_cannot_reference_another_case() -> None:
    with pytest.raises(ValidationError, match="does not match record case"):
        IngestedRecord(
            case_id="case_alpha-001",
            record_id="per_reg-001",
            record_type="person",
            observed_at=WHEN,
            data={"entity_id": "per_reg-001", "display_name": "Avery Rowan"},
            provenance=[
                ProvenanceRecord(
                    case_id="case_beta-001", source_record_id="src_beta-001", record_id="per_reg-001"
                )
            ],
        )


# ---------------------------------------------------------------------------
# 4-6  Validation boundary and fabricated facts
# ---------------------------------------------------------------------------


def test_nlp_output_satisfies_the_canonical_validation_boundary() -> None:
    """Every NLP record must survive the validator structured ingestion uses."""
    text = (
        "On 2026-01-09 18:30, Avery Rowan contacted Blair Keene using phone +1 (555) 010-2040. "
        "Avery drove vehicle ST-2040 at Demo Market. "
        "Avery was associated with Northstar Demo Cooperative in Example City. "
        "The incident, fictional handoff, was recorded."
    )
    _, records, _ = _pipeline(_report("case_bound-001", "src_bound-001", text))

    assert records
    for record in records:
        PAYLOAD_MODELS[record.record_type].model_validate(record.data)


def test_extraction_output_without_a_domain_record_is_reported_not_dropped() -> None:
    _, _, rejected = _pipeline(
        _report("case_bound-002", "src_bound-002", "On 2026-01-09 18:30, Avery Rowan met Blair Keene.")
    )

    assert any("DATE_TIME" in message for message in rejected)


def test_invalid_extraction_payload_is_reported_with_a_readable_reason() -> None:
    service = NLPExtractionService()
    report = _report("case_bound-003", "src_bound-003", "Avery Rowan met Blair Keene.")
    extraction = service.extract(report)

    record = service._build_record(
        report, extraction, "per_bad-001", "person", {"entity_id": "per_bad-001"}, [extraction.extracted_entities[0].span]
    )

    assert isinstance(record, str)
    assert "display_name" in record


def test_no_fabricated_attribute_values_are_produced() -> None:
    text = (
        "Avery Rowan drove vehicle ST-2040 at Demo Market. "
        "Avery was associated with Northstar Demo Cooperative in Example City. "
        "The incident, fictional handoff, was recorded."
    )
    _, records, _ = _pipeline(_report("case_fab-001", "src_fab-001", text))

    banned = {"Synthetic report vehicle", "Synthetic locality", "synthetic organization", "loc_nlp-unknown"}
    for record in records:
        for value in record.data.values():
            if isinstance(value, str):
                assert value not in banned, f"fabricated value {value!r} in {record.record_id}"

    vehicle = next(r for r in records if r.record_type == "vehicle")
    location = next(r for r in records if r.record_type == "location")
    organization = next(r for r in records if r.record_type == "organization")
    incident = next(r for r in records if r.record_type == "incident")

    assert vehicle.data["make_model"] is None
    assert location.data["locality"] is None
    assert organization.data["organization_type"] is None
    assert incident.data["location_id"] is None


def test_locations_with_unknown_locality_do_not_collapse_together() -> None:
    text = "Avery Rowan drove vehicle ST-2040 at Demo Market. Blair Keene was seen at Depot Yard."
    _, records, _ = _pipeline(_report("case_fab-002", "src_fab-002", text))

    locations = [record for record in records if record.record_type == "location"]
    labels = {record.data["label"] for record in locations}

    assert {"Demo Market", "Depot Yard"} <= labels
    assert len({record.record_id for record in locations}) == len(locations)


# ---------------------------------------------------------------------------
# 7-9  Provenance and assertion semantics
# ---------------------------------------------------------------------------


def test_provenance_preserves_character_spans_and_snippets() -> None:
    text = "Avery Rowan contacted Blair Keene."
    report = _report("case_prov-001", "src_prov-001", text)
    _, records, _ = _pipeline(report)

    person = next(r for r in records if r.record_type == "person")
    reference = person.provenance[0]

    assert reference.character_start is not None and reference.character_end is not None
    assert reference.snippet
    # The recorded span must actually quote the source document.
    assert text[reference.character_start:reference.character_end] == reference.snippet


def test_provenance_carries_full_source_identity() -> None:
    report = _report("case_prov-002", "src_prov-002", "Avery Rowan contacted Blair Keene.")
    extraction, records, _ = _pipeline(report)

    reference = records[0].provenance[0]

    assert reference.case_id == "case_prov-002"
    assert reference.source_record_id == "src_prov-002"
    # The document id must be the id the document is stored under, so the
    # reference resolves to a real document rather than to the report label.
    assert reference.document_id == report.source_record_id
    assert reference.content_hash == extraction.content_hash
    assert reference.extraction_run_id == extraction.extraction_run_id
    assert reference.source_type == "synthetic_report"


def test_malformed_provenance_fails_rather_than_becoming_misleading_evidence() -> None:
    base = {"case_id": "case_prov-003", "source_record_id": "src_prov-003", "record_id": "per_x"}

    with pytest.raises(ValidationError):
        ProvenanceRecord(**base, character_start=5)  # end missing
    with pytest.raises(ValidationError):
        ProvenanceRecord(**base, character_start=5, character_end=9)  # snippet missing
    with pytest.raises(ValidationError):
        ProvenanceRecord(**base, character_start=9, character_end=5, snippet="x")
    with pytest.raises(ValidationError):
        ProvenanceRecord(case_id="not-a-case", source_record_id="src_prov-003", record_id="per_x")


def test_spans_survive_all_the_way_to_the_evidence_api() -> None:
    report = {
        "case_id": "case_span-001",
        "report_id": "rpt_span-001",
        "source_record_id": "src_span-001",
        "observed_at": "2026-01-10T08:00:00Z",
        "text": "Avery Rowan contacted Blair Keene.",
    }
    processed = client.post("/api/nlp/process", json=report).json()
    graph = client.get(f"/api/graph/{processed['graph_id']}").json()

    node = next(n for n in graph["nodes"] if n["attributes"].get("display_name") == "Avery Rowan")
    evidence = client.get(f"/api/graph/{processed['graph_id']}/evidence/{node['node_id']}").json()

    assert evidence["evidence"]
    for reference in evidence["evidence"]:
        assert reference["character_start"] is not None
        assert reference["snippet"]
        assert reference["case_id"] == "case_span-001"


def test_assertion_semantics_survive_the_whole_pipeline() -> None:
    processed = client.post(
        "/api/nlp/process",
        json={
            "case_id": "case_sem-001",
            "report_id": "rpt_sem-001",
            "source_record_id": "src_sem-001",
            "observed_at": "2026-01-10T08:00:00Z",
            "text": "Avery Rowan contacted Blair Keene.",
        },
    ).json()
    graph = client.get(f"/api/graph/{processed['graph_id']}").json()

    # An NLP interpretation must never surface as an observed fact...
    assert all(edge["assertion_type"] == "inferred" for edge in graph["edges"])
    assert all(node["assertion_type"] == "inferred" for node in graph["nodes"])
    # ...while the span backing it is literally present in the document.
    assert all(
        reference["provenance_type"] == "observed"
        for node in graph["nodes"]
        for reference in node["provenance"]
    )


def test_unknown_assertions_reach_the_graph_as_unknown(make_record) -> None:
    records = [
        make_record(
            "per_unk-001",
            "person",
            {"entity_id": "per_unk-001", "display_name": "Avery Rowan"},
            case_id="case_unk-001",
            assertion_type="unknown",
        ),
    ]

    graph = KnowledgeGraphService().build("graph_unk-001", "case_unk-001", records)

    assert graph.nodes[0].assertion_type == "unknown"


def test_merging_records_never_strengthens_an_assertion(make_record) -> None:
    records = [
        make_record(
            "per_mix-001",
            "person",
            {"entity_id": "per_mix-001", "display_name": "Avery Rowan"},
            case_id="case_mix-001",
            assertion_type="observed",
        ),
        make_record(
            "per_mix-002",
            "person",
            {"entity_id": "per_mix-002", "display_name": "Avery Rowan"},
            case_id="case_mix-001",
            assertion_type="inferred",
        ),
    ]

    graph = KnowledgeGraphService().build("graph_mix-001", "case_mix-001", records)

    assert len(graph.nodes) == 1
    assert graph.nodes[0].assertion_type == "inferred"


# ---------------------------------------------------------------------------
# 10-11  Relationship attribution
# ---------------------------------------------------------------------------


def test_relationship_subject_is_the_actual_sentence_subject() -> None:
    """The confirmed defect: the first person in the document was always used."""
    text = "Avery Rowan filed the report. Blair Keene drove vehicle ST-9911 at Depot Yard."
    extraction, _, _ = _pipeline(_report("case_attr-001", "src_attr-001", text))

    names = {entity.entity_id: entity.text for entity in extraction.extracted_entities}
    uses = [r for r in extraction.extracted_relationships if r.relationship_type == "uses"]

    assert len(uses) == 1
    assert names[uses[0].source_entity_id] == "Blair Keene"
    assert names[uses[0].target_entity_id] == "ST-9911"


def test_relationship_with_no_subject_in_its_sentence_is_omitted() -> None:
    """A statement naming nobody must not acquire a subject from elsewhere."""
    text = "Avery Rowan filed the report. The incident, fictional handoff, was recorded."
    extraction, _, _ = _pipeline(_report("case_attr-002", "src_attr-002", text))

    assert [r for r in extraction.extracted_relationships if r.relationship_type == "involved_in"] == []


def test_vehicle_sighting_without_a_person_creates_no_relationship() -> None:
    text = "Vehicle ST-9911 was seen at Depot Yard."
    extraction, _, _ = _pipeline(_report("case_attr-003", "src_attr-003", text))

    assert extraction.extracted_relationships == []
    assert any("no relationship phrase" in warning for warning in extraction.warnings)


def test_ambiguous_short_name_does_not_become_a_relationship_subject() -> None:
    """Two people sharing a first name make a bare mention unusable."""
    text = "Avery Rowan filed the report. Avery Stone was present. Avery drove vehicle ST-9911."
    extraction, _, _ = _pipeline(_report("case_attr-004", "src_attr-004", text))

    uses = [r for r in extraction.extracted_relationships if r.relationship_type == "uses"]
    assert uses == []


@pytest.mark.parametrize(
    "text",
    [
        "Avery Rowan has not met Blair Keene.",
        "Avery Rowan never met Blair Keene.",
        "Avery Rowan denied that he contacted Blair Keene.",
    ],
)
def test_negated_statements_do_not_become_positive_relationships(text: str) -> None:
    """A negated claim must not be recorded as the relationship it denies."""
    extraction, _, _ = _pipeline(_report("case_neg-001", "src_neg-001", text))

    assert extraction.extracted_relationships == []
    assert any("negated" in warning for warning in extraction.warnings)


def test_positive_statements_are_unaffected_by_the_negation_guard() -> None:
    extraction, _, _ = _pipeline(_report("case_neg-002", "src_neg-002", "Avery Rowan met Blair Keene."))

    assert [r.relationship_type for r in extraction.extracted_relationships] == ["met"]


def test_place_names_are_not_also_reported_as_people() -> None:
    text = "Casey Vance travelled to River Bend and met Jordan Pike."
    extraction, _, _ = _pipeline(_report("case_attr-005", "src_attr-005", text))

    people = {e.text for e in extraction.extracted_entities if e.entity_type == "PERSON"}
    locations = {e.text for e in extraction.extracted_entities if e.entity_type == "LOCATION"}

    assert people == {"Casey Vance", "Jordan Pike"}
    assert "River Bend" in locations
    assert "River Bend" not in people


def test_extracted_datetime_is_attached_to_the_relationship_it_times() -> None:
    text = "On 2026-01-09 18:30, Avery Rowan contacted Blair Keene."
    extraction, _, _ = _pipeline(_report("case_attr-006", "src_attr-006", text))

    contacted = next(r for r in extraction.extracted_relationships if r.relationship_type == "contacted")

    assert contacted.occurred_at == datetime(2026, 1, 9, 18, 30)


# ---------------------------------------------------------------------------
# 12-15  Graph integrity and evidence
# ---------------------------------------------------------------------------


def test_graph_nodes_preserve_resolution_uncertainty(make_record) -> None:
    records = [
        make_record("org_rev-001", "organization", {"entity_id": "org_rev-001", "name": "Northstar Demo Cooperative"}, case_id="case_rev-001"),
        make_record("org_rev-002", "organization", {"entity_id": "org_rev-002", "name": "Northstar Demo Cooperatives"}, case_id="case_rev-001"),
    ]

    graph = KnowledgeGraphService().build("graph_rev-001", "case_rev-001", records)

    flagged = next(node for node in graph.nodes if node.match_status == "candidate_review")
    assert flagged.review_candidates
    assert 0.88 <= flagged.match_confidence < 1
    assert "org_rev-002" in graph.unresolved_record_ids


def test_edge_with_an_unresolvable_endpoint_is_rejected_not_left_dangling(make_record) -> None:
    records = [
        make_record("per_dang-001", "person", {"entity_id": "per_dang-001", "display_name": "Avery Rowan"}, case_id="case_dang-001"),
        make_record(
            "rel_dang-001",
            "relationship",
            {
                "record_id": "rel_dang-001",
                "from_entity_id": "per_dang-001",
                "to_entity_id": "inc_missing-001",
                "relationship_type": "involved_in",
                "source_record_id": "src_test-001",
                "confidence": 0.9,
            },
            case_id="case_dang-001",
        ),
    ]

    graph = KnowledgeGraphService().build("graph_dang-001", "case_dang-001", records)

    assert graph.edges == []
    assert len(graph.rejected_edges) == 1
    assert "inc_missing-001" in graph.rejected_edges[0].reason


def test_repeated_assertions_merge_into_one_edge_with_pooled_evidence(make_record) -> None:
    def relationship(record_id: str, source_record_id: str, confidence: float):
        return make_record(
            record_id,
            "relationship",
            {
                "record_id": record_id,
                "from_entity_id": "per_dup-001",
                "to_entity_id": "phn_dup-001",
                "relationship_type": "uses",
                "source_record_id": source_record_id,
                "confidence": confidence,
            },
            case_id="case_dup-001",
            source_record_id=source_record_id,
        )

    records = [
        make_record("per_dup-001", "person", {"entity_id": "per_dup-001", "display_name": "Avery Rowan"}, case_id="case_dup-001"),
        make_record("phn_dup-001", "phone", {"entity_id": "phn_dup-001", "number": "+15550101"}, case_id="case_dup-001"),
        relationship("rel_dup-001", "src_dup-001", 0.9),
        relationship("rel_dup-002", "src_dup-002", 0.4),
    ]

    graph = KnowledgeGraphService().build("graph_dup-001", "case_dup-001", records)

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert len({e.edge_id for e in graph.edges}) == len(graph.edges)
    assert sorted(edge.source_record_ids) == ["rel_dup-001", "rel_dup-002"]
    assert {r.source_record_id for r in edge.provenance} == {"src_dup-001", "src_dup-002"}
    assert edge.confidence == 0.9


def test_evidence_lookup_returns_every_supporting_record(make_record) -> None:
    records = [
        make_record("per_ev-001", "person", {"entity_id": "per_ev-001", "display_name": "Avery Rowan"}, case_id="case_ev-001", source_record_id="src_ev-001"),
        make_record("per_ev-002", "person", {"entity_id": "per_ev-002", "display_name": "Avery Rowan"}, case_id="case_ev-001", source_record_id="src_ev-002"),
    ]
    payload = {
        "graph_id": "graph_ev-001",
        "case_id": "case_ev-001",
        "records": [record.model_dump(mode="json") for record in records],
    }
    graph = client.post("/api/graph", json=payload).json()
    node_id = graph["nodes"][0]["node_id"]

    evidence = client.get(f"/api/graph/graph_ev-001/evidence/{node_id}").json()

    assert {r["source_record_id"] for r in evidence["evidence"]} == {"src_ev-001", "src_ev-002"}


def test_graph_rejects_duplicate_node_ids_at_the_contract_level() -> None:
    from app.schemas.graph import KnowledgeGraph, KnowledgeGraphNode

    def node() -> KnowledgeGraphNode:
        return KnowledgeGraphNode(
            case_id="case_dupnode-001",
            node_id="per_same-001",
            entity_type="person",
            attributes={"entity_id": "per_same-001"},
            source_entity_ids=["per_same-001"],
            provenance=[ProvenanceRecord(case_id="case_dupnode-001", source_record_id="src_x-001", record_id="per_same-001")],
            match_confidence=1.0,
            match_status="canonical",
        )

    with pytest.raises(ValidationError, match="duplicate node_id"):
        KnowledgeGraph(graph_id="graph_dupnode-001", case_id="case_dupnode-001", nodes=[node(), node()])


# ---------------------------------------------------------------------------
# 16  Pipeline reconnection
# ---------------------------------------------------------------------------


def test_process_produces_a_graph_retrievable_through_the_graph_api() -> None:
    report = {
        "case_id": "case_flow-001",
        "report_id": "rpt_flow-001",
        "source_record_id": "src_flow-001",
        "observed_at": "2026-01-10T08:00:00Z",
        "text": "On 2026-01-09 18:30, Avery Rowan contacted Blair Keene using phone +1 (555) 010-2040.",
    }

    processed = client.post("/api/nlp/process", json=report)
    assert processed.status_code == 200
    body = processed.json()

    fetched = client.get(f"/api/graph/{body['graph_id']}")
    assert fetched.status_code == 200
    graph = fetched.json()
    assert graph["case_id"] == "case_flow-001"
    assert len(graph["nodes"]) == body["graph_node_count"]
    assert len(graph["edges"]) == body["graph_edge_count"]


def test_second_report_folds_into_the_same_case_graph() -> None:
    base = {
        "case_id": "case_flow-002",
        "source_record_id": "src_flow-002a",
        "observed_at": "2026-01-10T08:00:00Z",
    }
    first = client.post(
        "/api/nlp/process",
        json={**base, "report_id": "rpt_flow-002", "text": "Avery Rowan contacted Blair Keene."},
    ).json()
    second = client.post(
        "/api/nlp/process",
        json={
            **base,
            "report_id": "rpt_flow-003",
            "source_record_id": "src_flow-002b",
            "text": "Blair Keene drove vehicle ST-9911 at Depot Yard.",
        },
    ).json()

    assert first["graph_id"] == second["graph_id"]
    assert second["graph_node_count"] > first["graph_node_count"]

    graph = client.get(f"/api/graph/{second['graph_id']}").json()
    blair = [n for n in graph["nodes"] if n["attributes"].get("display_name") == "Blair Keene"]
    assert len(blair) == 1, "the same person across two reports must be one node"


def test_a_graph_cannot_receive_records_from_a_different_case() -> None:
    shared = {
        "report_id": "rpt_flow-004",
        "source_record_id": "src_flow-004",
        "observed_at": "2026-01-10T08:00:00Z",
        "text": "Avery Rowan contacted Blair Keene.",
        "graph_id": "graph_shared-001",
    }
    assert client.post("/api/nlp/process", json={**shared, "case_id": "case_flow-004"}).status_code == 200

    response = client.post("/api/nlp/process", json={**shared, "case_id": "case_flow-005"})

    assert response.status_code == 422
    assert "case_flow-004" in response.json()["detail"]
