"""Stage B: persistence, case isolation, and survival across a restart.

The restart tests are the point of this file. Persistence that is only ever
observed through the same live Python objects that wrote it proves nothing, so
these tests either throw the entire engine away and rebuild it from the database
URL, or write from a genuinely separate operating-system process and read the
result back here.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.db.repositories import (
    CaseRepository,
    GraphRepository,
    ProjectionRepository,
    RecordRepository,
    RunRepository,
)
from app.main import app
from app.schemas.investigation import IngestedRecord, ProvenanceRecord
from app.services.demo_seed import load_dataset, seed_demo_case
from app.services.pipeline import InvestigationPipeline, default_graph_id

client = TestClient(app)

BACKEND_ROOT = Path(__file__).resolve().parent.parent

REPORT_TEXT = (
    "On 2026-01-09 18:30, Avery Rowan contacted Blair Keene using phone "
    "+1 (555) 010-2040. Avery drove vehicle ST-2040 at Demo Market and met Blair Keene."
)


def _report(case_id: str, *, report_id: str, source_record_id: str, text: str = REPORT_TEXT) -> dict:
    return {
        "case_id": case_id,
        "report_id": report_id,
        "source_record_id": source_record_id,
        "observed_at": "2026-01-10T08:00:00Z",
        "text": text,
    }


def _process(case_id: str, suffix: str, text: str = REPORT_TEXT) -> dict:
    response = client.post(
        "/api/nlp/process",
        json=_report(case_id, report_id=f"rpt_{suffix}", source_record_id=f"src_{suffix}", text=text),
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 1  The investigation lifecycle is persisted
# ---------------------------------------------------------------------------


def test_investigation_can_be_created_listed_and_fetched() -> None:
    created = client.post(
        "/api/investigations",
        json={
            "case_id": "case_life-001",
            "title": "Synthetic demonstration investigation",
            "description": "Fictional records only.",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["case_id"] == "case_life-001"
    assert created.json()["status"] == "open"

    listed = client.get("/api/investigations").json()
    assert listed["count"] == 1
    assert listed["investigations"][0]["title"] == "Synthetic demonstration investigation"

    fetched = client.get("/api/investigations/case_life-001")
    assert fetched.status_code == 200
    assert fetched.json()["record_count"] == 0
    assert fetched.json()["entity_count"] == 0


def test_creating_the_same_investigation_twice_is_refused() -> None:
    payload = {"case_id": "case_dup-b001", "title": "First"}
    assert client.post("/api/investigations", json=payload).status_code == 201
    conflict = client.post("/api/investigations", json={**payload, "title": "Second"})
    assert conflict.status_code == 409


def test_pipeline_persists_the_full_chain_from_document_to_graph() -> None:
    """Case -> document -> run -> record -> evidence -> entity -> relationship -> graph."""
    body = _process("case_chain-001", "chain-001")

    summary = client.get("/api/investigations/case_chain-001").json()
    assert summary["document_count"] == 1
    assert summary["run_count"] == 1
    assert summary["record_count"] > 0
    assert summary["entity_count"] == body["graph_node_count"]
    assert summary["relationship_count"] == body["graph_edge_count"]
    assert summary["graph_id"] == body["graph_id"]

    evidence = client.get("/api/investigations/case_chain-001/evidence").json()
    assert evidence["count"] > 0
    assert all(item["case_id"] == "case_chain-001" for item in evidence["evidence"])


def test_structured_ingestion_persists_records_and_documents(session) -> None:
    dataset = load_dataset()
    pipeline = InvestigationPipeline()
    result = pipeline.ingest_dataset(session, dataset)

    assert result.accepted_count > 0
    case_id = dataset.case_id
    assert CaseRepository(session).get(case_id) is not None
    assert RecordRepository(session).count(case_id) == result.accepted_count

    runs = RunRepository(session).list_for_case(case_id)
    assert len(runs) == 1
    assert runs[0].kind == "structured"
    assert runs[0].status == "completed"
    assert runs[0].completed_at is not None


# ---------------------------------------------------------------------------
# 2  Case isolation
# ---------------------------------------------------------------------------


def _two_cases_with_identical_source_text() -> tuple[dict, dict]:
    first = _process("case_iso-a", "iso-a")
    second = _process("case_iso-b", "iso-b")
    return first, second


def test_case_a_cannot_retrieve_case_b_entities() -> None:
    _two_cases_with_identical_source_text()

    a = client.get("/api/investigations/case_iso-a/entities").json()
    b = client.get("/api/investigations/case_iso-b/entities").json()

    assert a["count"] > 0 and b["count"] > 0
    assert all(entity["case_id"] == "case_iso-a" for entity in a["entities"])
    assert all(entity["case_id"] == "case_iso-b" for entity in b["entities"])

    a_ids = {entity["canonical_id"] for entity in a["entities"]}
    b_ids = {entity["canonical_id"] for entity in b["entities"]}
    assert not (a_ids & b_ids), "identical descriptions in two cases must not share an identity"


def test_case_a_cannot_retrieve_case_b_relationships() -> None:
    _two_cases_with_identical_source_text()

    a = client.get("/api/investigations/case_iso-a/relationships").json()
    b = client.get("/api/investigations/case_iso-b/relationships").json()

    assert a["count"] > 0 and b["count"] > 0
    assert all(item["case_id"] == "case_iso-a" for item in a["relationships"])
    assert all(item["case_id"] == "case_iso-b" for item in b["relationships"])
    assert not (
        {item["relationship_id"] for item in a["relationships"]}
        & {item["relationship_id"] for item in b["relationships"]}
    )


def test_case_a_cannot_retrieve_case_b_evidence() -> None:
    _two_cases_with_identical_source_text()

    a = client.get("/api/investigations/case_iso-a/evidence").json()
    b = client.get("/api/investigations/case_iso-b/evidence").json()

    assert a["count"] > 0 and b["count"] > 0
    assert all(item["case_id"] == "case_iso-a" for item in a["evidence"])
    assert all(item["case_id"] == "case_iso-b" for item in b["evidence"])
    assert not (
        {item["provenance_id"] for item in a["evidence"]}
        & {item["provenance_id"] for item in b["evidence"]}
    )
    assert {item["source_record_id"] for item in a["evidence"]} == {"src_iso-a"}
    assert {item["source_record_id"] for item in b["evidence"]} == {"src_iso-b"}


def test_case_a_cannot_retrieve_case_b_graph() -> None:
    _two_cases_with_identical_source_text()

    a = client.get("/api/investigations/case_iso-a/graph").json()
    b = client.get("/api/investigations/case_iso-b/graph").json()

    assert a["case_id"] == "case_iso-a"
    assert b["case_id"] == "case_iso-b"
    assert a["graph_id"] != b["graph_id"]
    assert not (
        {node["node_id"] for node in a["nodes"]} & {node["node_id"] for node in b["nodes"]}
    )
    assert all(node["case_id"] == "case_iso-a" for node in a["nodes"])
    assert all(node["case_id"] == "case_iso-b" for node in b["nodes"])


@pytest.mark.parametrize(
    "path",
    ["", "/entities", "/relationships", "/evidence", "/documents", "/runs", "/graph"],
)
def test_a_nonexistent_case_is_not_found(path: str) -> None:
    response = client.get(f"/api/investigations/case_missing-001{path}")
    assert response.status_code == 404
    assert "case_missing-001" in response.json()["detail"]


def test_an_existing_case_with_no_data_is_empty_not_missing() -> None:
    client.post("/api/investigations", json={"case_id": "case_empty-001", "title": "Empty"})

    entities = client.get("/api/investigations/case_empty-001/entities")
    relationships = client.get("/api/investigations/case_empty-001/relationships")
    evidence = client.get("/api/investigations/case_empty-001/evidence")
    documents = client.get("/api/investigations/case_empty-001/documents")
    runs = client.get("/api/investigations/case_empty-001/runs")
    graph = client.get("/api/investigations/case_empty-001/graph")

    assert entities.status_code == 200 and entities.json()["count"] == 0
    assert relationships.status_code == 200 and relationships.json()["count"] == 0
    assert evidence.status_code == 200 and evidence.json()["count"] == 0
    assert documents.status_code == 200 and documents.json()["count"] == 0
    assert runs.status_code == 200 and runs.json()["count"] == 0
    assert graph.status_code == 200
    assert graph.json()["nodes"] == [] and graph.json()["edges"] == []


def test_documents_endpoint_resolves_the_document_an_evidence_row_names() -> None:
    """Evidence names a ``document_id``; this is what makes it followable.

    Without this the provenance chain stops one step short of the source, so the
    test asserts the join actually closes rather than that the route responds.
    """
    _process("case_docs-001", "docs-001")

    documents = client.get("/api/investigations/case_docs-001/documents").json()
    assert documents["count"] == 1
    document = documents["documents"][0]
    assert document["case_id"] == "case_docs-001"
    assert document["content"], "the stored document keeps the text its spans quote"

    evidence = client.get("/api/investigations/case_docs-001/evidence").json()
    referenced = {row["document_id"] for row in evidence["evidence"] if row["document_id"]}
    assert referenced == {document["document_id"]}

    spans = [row for row in evidence["evidence"] if row["character_start"] is not None]
    assert spans, "an NLP report should yield at least one quoted span"
    for row in spans:
        quoted = document["content"][row["character_start"] : row["character_end"]]
        assert quoted == row["snippet"], "the stored span must still quote the stored document"


def test_runs_endpoint_resolves_the_extraction_run_an_evidence_row_names() -> None:
    _process("case_runs-001", "runs-001")

    runs = client.get("/api/investigations/case_runs-001/runs").json()
    assert runs["count"] == 1
    run = runs["runs"][0]
    assert run["kind"] == "nlp"
    assert run["status"] == "completed"
    assert run["completed_at"] is not None

    evidence = client.get("/api/investigations/case_runs-001/evidence").json()
    named = {
        row["extraction_run_id"]
        for row in evidence["evidence"]
        if row["extraction_run_id"]
    }
    assert named == {run["run_id"]}


def test_documents_and_runs_stay_within_their_case() -> None:
    _process("case_iso-a", "iso-a")
    _process("case_iso-b", "iso-b")

    a_documents = client.get("/api/investigations/case_iso-a/documents").json()
    b_documents = client.get("/api/investigations/case_iso-b/documents").json()
    assert all(item["case_id"] == "case_iso-a" for item in a_documents["documents"])
    assert all(item["case_id"] == "case_iso-b" for item in b_documents["documents"])
    assert not (
        {item["document_id"] for item in a_documents["documents"]}
        & {item["document_id"] for item in b_documents["documents"]}
    )

    a_runs = client.get("/api/investigations/case_iso-a/runs").json()
    b_runs = client.get("/api/investigations/case_iso-b/runs").json()
    assert all(item["case_id"] == "case_iso-a" for item in a_runs["runs"])
    assert all(item["case_id"] == "case_iso-b" for item in b_runs["runs"])


def test_persistence_refuses_a_record_from_another_case(session) -> None:
    foreign = IngestedRecord(
        case_id="case_other-b001",
        record_id="per_other-b001",
        record_type="person",
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data={"entity_id": "per_other-b001", "display_name": "Avery Rowan"},
        provenance=[
            ProvenanceRecord(
                case_id="case_other-b001",
                source_record_id="src_other-b001",
                record_id="per_other-b001",
            )
        ],
    )
    CaseRepository(session).ensure("case_host-b001", "Host")
    session.flush()

    with pytest.raises(ValueError, match="cannot cross a case boundary"):
        RecordRepository(session).upsert_many("case_host-b001", [foreign])


def test_a_graph_id_cannot_be_reused_by_a_second_case() -> None:
    shared = {"graph_id": "graph_shared-b001"}
    first = client.post(
        "/api/nlp/process",
        json={**_report("case_share-a", report_id="rpt_share-a", source_record_id="src_share-a"), **shared},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/nlp/process",
        json={**_report("case_share-b", report_id="rpt_share-b", source_record_id="src_share-b"), **shared},
    )
    assert second.status_code == 422
    assert "case_share-a" in second.json()["detail"]


def test_projection_refuses_a_graph_belonging_to_another_case(session) -> None:
    pipeline = InvestigationPipeline()
    CaseRepository(session).ensure("case_proj-a", "A")
    CaseRepository(session).ensure("case_proj-b", "B")
    session.flush()

    record = IngestedRecord(
        case_id="case_proj-a",
        record_id="per_proj-a",
        record_type="person",
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data={"entity_id": "per_proj-a", "display_name": "Avery Rowan"},
        provenance=[
            ProvenanceRecord(
                case_id="case_proj-a", source_record_id="src_proj-a", record_id="per_proj-a"
            )
        ],
    )
    RecordRepository(session).upsert_many("case_proj-a", [record])
    graph = pipeline.graph_service.build("graph_proj-a", "case_proj-a", [record])

    with pytest.raises(ValueError, match="case_proj-a"):
        ProjectionRepository(session).replace("case_proj-b", graph)

    with pytest.raises(ValueError, match="case_proj-a"):
        GraphRepository(session).save("case_proj-b", graph)


# ---------------------------------------------------------------------------
# 3  Survival across a restart
# ---------------------------------------------------------------------------


def _rebuild_engine_from_scratch(url: str) -> None:
    """Throw the engine away entirely, then build a new one from the URL alone."""
    database.dispose()
    assert database._engine is None, "the engine must be genuinely gone"
    assert database._session_factory is None
    database.configure(url)


def test_investigation_survives_destroying_and_rebuilding_the_engine(tmp_path) -> None:
    db_path = tmp_path / "restart.db"
    url = f"sqlite:///{db_path.as_posix()}"

    database.configure(url)
    database.create_all()

    with database.session_scope() as session:
        summary = seed_demo_case(session)

    case_id = summary.case_id
    expected_entities = summary.node_count
    expected_edges = summary.edge_count
    assert expected_entities > 0 and expected_edges > 0

    _rebuild_engine_from_scratch(url)

    with database.session_scope() as session:
        assert CaseRepository(session).get(case_id) is not None

        entities = ProjectionRepository(session).list_entities(case_id)
        relationships = ProjectionRepository(session).list_relationships(case_id)
        evidence = RecordRepository(session).list_evidence(case_id)
        graph = GraphRepository(session).current_for_case(case_id)

        assert len(entities) == expected_entities
        assert len(relationships) == expected_edges
        assert len(evidence) > 0
        assert graph is not None
        assert len(graph.nodes) == expected_entities
        assert len(graph.edges) == expected_edges
        assert all(node.provenance for node in graph.nodes)
        assert all(entity.case_id == case_id for entity in entities)


def test_investigation_written_by_another_process_is_readable_here(tmp_path) -> None:
    """The strongest form of the requirement: a different OS process wrote this."""
    db_path = tmp_path / "subprocess.db"
    url = f"sqlite:///{db_path.as_posix()}"

    writer = (
        "from app.db.database import create_all, session_scope;"
        "from app.services.demo_seed import seed_demo_case;"
        "import json;"
        "create_all();"
        "session = session_scope();"
        "s = session.__enter__();"
        "summary = seed_demo_case(s);"
        "session.__exit__(None, None, None);"
        "print(json.dumps(summary.model_dump()))"
    )
    environment = {**os.environ, "SILENT_TRACE_DATABASE_URL": url}
    completed = subprocess.run(
        [sys.executable, "-c", writer],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, f"writer process failed:\n{completed.stderr}"
    written = json.loads(completed.stdout.strip().splitlines()[-1])

    assert db_path.exists(), "the writer process must have created a real database file"

    # This process has never held a session on that database.
    database.configure(url)
    with database.session_scope() as session:
        case_id = written["case_id"]
        assert CaseRepository(session).get(case_id) is not None
        assert len(ProjectionRepository(session).list_entities(case_id)) == written["node_count"]
        assert len(ProjectionRepository(session).list_relationships(case_id)) == written["edge_count"]

        graph = GraphRepository(session).current_for_case(case_id)
        assert graph is not None
        assert len(graph.nodes) == written["node_count"]
        assert len(graph.edges) == written["edge_count"]

        records = RecordRepository(session).list_for_case(case_id)
        assert len(records) > 0
        assert all(record.case_id == case_id for record in records)
        assert all(record.provenance for record in records)


def test_reloaded_graph_is_identical_to_the_one_that_was_built(tmp_path) -> None:
    db_path = tmp_path / "identical.db"
    url = f"sqlite:///{db_path.as_posix()}"
    database.configure(url)
    database.create_all()

    pipeline = InvestigationPipeline()
    with database.session_scope() as session:
        seed_demo_case(session, pipeline)
        before = pipeline.graph_for_case(session, "case_demo-001").model_dump(mode="json")

    _rebuild_engine_from_scratch(url)

    with database.session_scope() as session:
        after = pipeline.graph_for_case(session, "case_demo-001").model_dump(mode="json")

    assert after == before, "a reloaded graph must not differ from the graph that was stored"


# ---------------------------------------------------------------------------
# 4  Semantics that must not be lost in storage
# ---------------------------------------------------------------------------


def test_character_spans_and_snippets_survive_persistence() -> None:
    _process("case_span-001", "span-001")

    evidence = client.get("/api/investigations/case_span-001/evidence").json()["evidence"]
    spanned = [item for item in evidence if item["character_start"] is not None]

    assert spanned, "NLP evidence must retain the span it was extracted from"
    for item in spanned:
        assert item["character_end"] > item["character_start"]
        assert item["snippet"]
        assert REPORT_TEXT[item["character_start"] : item["character_end"]] == item["snippet"]


def test_observed_and_inferred_semantics_survive_persistence(session) -> None:
    pipeline = InvestigationPipeline()
    dataset = load_dataset()
    pipeline.ingest_dataset(session, dataset)

    structured = ProjectionRepository(session).list_entities(dataset.case_id)
    assert structured, "structured ingestion must produce entities"
    assert all(entity.assertion_type == "observed" for entity in structured)

    client.post(
        "/api/nlp/process",
        json=_report("case_sem-001", report_id="rpt_sem-001", source_record_id="src_sem-001"),
    )
    inferred = client.get("/api/investigations/case_sem-001/entities").json()["entities"]
    assert inferred
    assert all(entity["assertion_type"] == "inferred" for entity in inferred)

    evidence = client.get("/api/investigations/case_sem-001/evidence").json()["evidence"]
    spanned = [item for item in evidence if item["character_start"] is not None]
    assert spanned
    assert all(item["provenance_type"] == "observed" for item in spanned), (
        "an inferred claim is still backed by an observed span"
    )


def test_resolution_uncertainty_survives_persistence(make_record, session) -> None:
    pipeline = InvestigationPipeline()
    records = [
        make_record(
            "per_unc-001",
            "person",
            {"entity_id": "per_unc-001", "display_name": "Jonathan Reyes"},
            case_id="case_unc-001",
            source_record_id="src_unc-001",
        ),
        make_record(
            "per_unc-002",
            "person",
            {"entity_id": "per_unc-002", "display_name": "Jonathon Reyes"},
            case_id="case_unc-001",
            source_record_id="src_unc-001",
        ),
    ]
    pipeline.build_graph(session, "graph_unc-001", "case_unc-001", records)

    stored = ProjectionRepository(session).list_entities("case_unc-001")
    statuses = {entity.match_status for entity in stored}
    assert "candidate_review" in statuses, "a near-match must stay flagged for review once stored"

    flagged = next(e for e in stored if e.match_status == "candidate_review")
    assert flagged.review_candidates
    assert 0 < flagged.match_confidence < 1


def test_persisted_relationships_reference_persisted_entities() -> None:
    _process("case_ref-001", "ref-001")

    entities = client.get("/api/investigations/case_ref-001/entities").json()["entities"]
    relationships = client.get("/api/investigations/case_ref-001/relationships").json()[
        "relationships"
    ]

    known = {entity["canonical_id"] for entity in entities}
    assert relationships
    for relationship in relationships:
        assert relationship["from_entity_id"] in known
        assert relationship["to_entity_id"] in known
        assert relationship["evidence_count"] > 0


def test_no_persisted_field_scores_guilt_or_criminality() -> None:
    _process("case_ethics-001", "ethics-001")

    entities = client.get("/api/investigations/case_ethics-001/entities").json()["entities"]
    relationships = client.get("/api/investigations/case_ethics-001/relationships").json()[
        "relationships"
    ]

    banned = {"guilt", "risk", "criminal", "suspicion", "threat", "danger", "score"}
    for payload in (*entities, *relationships):
        for field in payload:
            assert not any(word in field.lower() for word in banned), (
                f"persisted field '{field}' implies a criminality judgement"
            )


# ---------------------------------------------------------------------------
# 5  Snapshots, determinism and the single write path
# ---------------------------------------------------------------------------


def test_each_pipeline_run_appends_a_graph_version(session) -> None:
    pipeline = InvestigationPipeline()
    first = _report("case_ver-001", report_id="rpt_ver-001", source_record_id="src_ver-001")
    second = _report(
        "case_ver-001",
        report_id="rpt_ver-002",
        source_record_id="src_ver-002",
        text="Blair Keene drove vehicle ST-9911 at Depot Yard.",
    )
    from app.schemas.nlp import ReportRequest

    pipeline.process_report(session, ReportRequest.model_validate(first))
    pipeline.process_report(session, ReportRequest.model_validate(second))

    versions = GraphRepository(session).versions_for_case("case_ver-001")
    assert [v.version for v in versions] == [1, 2]
    assert [v.is_current for v in versions] == [False, True]
    assert versions[1].node_count > versions[0].node_count


def test_seeding_the_demo_case_twice_changes_nothing(session) -> None:
    pipeline = InvestigationPipeline()

    first = seed_demo_case(session, pipeline)
    entities_after_first = {
        entity.canonical_id for entity in ProjectionRepository(session).list_entities(first.case_id)
    }
    records_after_first = RecordRepository(session).count(first.case_id)

    second = seed_demo_case(session, pipeline)
    entities_after_second = {
        entity.canonical_id for entity in ProjectionRepository(session).list_entities(second.case_id)
    }

    assert second.node_count == first.node_count
    assert second.edge_count == first.edge_count
    assert RecordRepository(session).count(second.case_id) == records_after_first
    assert entities_after_second == entities_after_first, "seeding is deterministic, not additive"


def test_the_demo_case_is_reachable_through_the_persistent_api(session) -> None:
    seed_demo_case(session)
    session.commit()

    listed = client.get("/api/investigations").json()
    assert any(item["case_id"] == "case_demo-001" for item in listed["investigations"])

    summary = client.get("/api/investigations/case_demo-001").json()
    assert summary["record_count"] > 0
    assert summary["entity_count"] > 0
    assert summary["document_count"] > 0

    graph = client.get("/api/investigations/case_demo-001/graph").json()
    assert graph["case_id"] == "case_demo-001"
    assert len(graph["nodes"]) == summary["entity_count"]


def test_the_in_memory_graph_store_no_longer_exists() -> None:
    """There must be exactly one write path, not a surviving parallel store."""
    with pytest.raises(ModuleNotFoundError):
        __import__("app.services.graph_store")


def test_graph_api_and_investigation_api_return_the_same_graph() -> None:
    body = _process("case_same-001", "same-001")

    by_graph_id = client.get(f"/api/graph/{body['graph_id']}").json()
    by_case = client.get("/api/investigations/case_same-001/graph").json()

    assert by_graph_id == by_case, "one graph must not have two different representations"
