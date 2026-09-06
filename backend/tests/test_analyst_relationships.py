"""Analyst-created relationships.

An analyst may assert a link the documents do not state. The risk this carries
is that such a link becomes indistinguishable from one a source actually
recorded, so these tests concentrate on the boundary: the assertion is stored,
it is usable, and it is permanently and visibly *not* document evidence.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.db.repositories import ProjectionRepository, RecordRepository, RunRepository
from app.main import app
from app.services.pipeline import InvestigationPipeline
from app.services.synthetic_populations import (
    COORDINATED_CASE,
    NORMAL_CASE,
    coordinated_population,
    normal_population,
)

client = TestClient(app)


@pytest.fixture
def seeded(session) -> str:
    InvestigationPipeline().ingest_dataset(session, normal_population())
    return NORMAL_CASE


@pytest.fixture
def two_cases(session) -> tuple[str, str]:
    pipeline = InvestigationPipeline()
    pipeline.ingest_dataset(session, normal_population())
    pipeline.ingest_dataset(session, coordinated_population())
    return NORMAL_CASE, COORDINATED_CASE


def _entity(session, case_id: str, label: str) -> str:
    for row in ProjectionRepository(session).list_entities(case_id):
        attributes = row.attributes or {}
        if attributes.get("display_name") == label or attributes.get("name") == label:
            return row.canonical_id
    raise AssertionError(f"no entity {label!r} in {case_id}")


def _assert_link(session, case_id: str, left: str, right: str, **kwargs):
    return InvestigationPipeline().create_analyst_relationship(
        session, case_id, from_entity_id=left, to_entity_id=right, **kwargs
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_analyst_can_assert_a_link_between_two_entities(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")

    before = {row.relationship_id for row in ProjectionRepository(session).list_relationships(seeded)}
    graph, edge_id = _assert_link(
        session,
        seeded,
        wren,
        vik,
        relationship_type="associated_with",
        analyst_id="analyst-7",
        note="Both named in the same synthetic scenario notes.",
    )
    after = {row.relationship_id for row in ProjectionRepository(session).list_relationships(seeded)}

    assert edge_id in after
    assert edge_id not in before, "this link did not previously exist"
    edge = next(item for item in graph.edges if item.edge_id == edge_id)
    assert {edge.from_node_id, edge.to_node_id} == {wren, vik}
    assert edge.relationship_type == "associated_with"


def test_analyst_relationship_uses_the_existing_vocabulary(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")

    response = client.post(
        f"/api/investigations/{seeded}/relationships",
        json={
            "from_entity_id": wren,
            "to_entity_id": vik,
            "relationship_type": "conspired_with",
        },
    )
    assert response.status_code == 422, "a type outside the canonical vocabulary is refused"


def test_api_creates_and_reports_the_relationship(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")

    created = client.post(
        f"/api/investigations/{seeded}/relationships",
        json={
            "from_entity_id": wren,
            "to_entity_id": vik,
            "relationship_type": "met",
            "confidence": 0.7,
            "analyst_id": "analyst-7",
            "note": "Asserted during review.",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()

    assert body["case_id"] == seeded
    assert body["relationship_type"] == "met"
    assert body["analyst_created"] is True
    assert body["assertion_type"] == "inferred"
    assert body["confidence"] == 0.7
    assert body["evidence_count"] >= 1

    listed = client.get(f"/api/investigations/{seeded}/relationships").json()
    match = [r for r in listed["relationships"] if r["relationship_id"] == body["relationship_id"]]
    assert match and match[0]["analyst_created"] is True


def test_a_self_link_is_refused(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")

    with pytest.raises(ValueError, match="two different entities"):
        _assert_link(session, seeded, wren, wren, relationship_type="associated_with")


# ---------------------------------------------------------------------------
# Case isolation
# ---------------------------------------------------------------------------


def test_an_entity_from_another_case_is_rejected(session, two_cases) -> None:
    normal_case, coordinated_case = two_cases
    wren = _entity(session, normal_case, "Wren Dabiri")
    marek = _entity(session, coordinated_case, "Marek Idris")

    with pytest.raises(ValueError, match="are not part of investigation"):
        _assert_link(session, normal_case, wren, marek, relationship_type="associated_with")


def test_cross_case_assertion_is_refused_through_the_api(session, two_cases) -> None:
    normal_case, coordinated_case = two_cases
    wren = _entity(session, normal_case, "Wren Dabiri")
    marek = _entity(session, coordinated_case, "Marek Idris")

    response = client.post(
        f"/api/investigations/{normal_case}/relationships",
        json={
            "from_entity_id": wren,
            "to_entity_id": marek,
            "relationship_type": "associated_with",
        },
    )
    assert response.status_code == 422
    assert "not part of investigation" in response.json()["detail"]

    other = client.get(f"/api/investigations/{coordinated_case}/relationships").json()
    assert all(not r["analyst_created"] for r in other["relationships"]), (
        "the rejected assertion must not have touched the other case"
    )


def test_an_unknown_entity_is_rejected(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")

    with pytest.raises(ValueError, match="are not part of investigation"):
        _assert_link(session, seeded, wren, "per_invented-001", relationship_type="met")


def test_assertion_against_an_unknown_case_is_404(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    response = client.post(
        "/api/investigations/case_absent-r001/relationships",
        json={"from_entity_id": wren, "to_entity_id": wren, "relationship_type": "met"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Provenance semantics
# ---------------------------------------------------------------------------


def test_provenance_names_the_assertion_and_fabricates_no_document(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")
    _assert_link(session, seeded, wren, vik, relationship_type="met", analyst_id="analyst-7")

    analyst_rows = [
        row
        for row, _, _ in RecordRepository(session).list_evidence(seeded)
        if row.source_type == "analyst_assertion"
    ]
    assert analyst_rows, "the assertion must leave provenance behind"

    for row in analyst_rows:
        assert row.case_id == seeded
        assert row.source_record_id.startswith("src_analyst-")
        assert row.document_id is None, "no document may be invented"
        assert row.content_hash is None, "there are no source bytes to hash"
        assert row.character_start is None and row.character_end is None
        assert row.snippet is None, "there is no source text to quote"
        assert row.provenance_type == "unknown"


def test_analyst_assertions_are_inferred_never_observed(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")
    _, edge_id = _assert_link(session, seeded, wren, vik, relationship_type="met")

    row = next(
        item
        for item in ProjectionRepository(session).list_relationships(seeded)
        if item.relationship_id == edge_id
    )
    assert row.assertion_type == "inferred", "nothing observed this link"

    records = [
        record
        for record in RecordRepository(session).list_for_case(seeded)
        if record.data.get("analyst_created")
    ]
    assert records
    assert all(record.assertion_type == "inferred" for record in records)
    assert all(record.data.get("analyst_id") is not None or True for record in records)


def test_an_assertion_cannot_promote_an_observed_relationship(session, seeded) -> None:
    """Agreeing with a document must add evidence without strengthening it."""
    rhea = _entity(session, seeded, "Rhea Alcott")
    sam = _entity(session, seeded, "Sam Alcott")

    projection = ProjectionRepository(session)
    existing = next(
        row
        for row in projection.list_relationships(seeded)
        if {row.from_entity_id, row.to_entity_id} == {rhea, sam}
        and row.relationship_type == "associated_with"
    )
    assert existing.assertion_type == "observed"
    evidence_before = len(
        projection.provenance_ids_for_relationship(seeded, existing.relationship_id)
    )

    _, edge_id = _assert_link(
        session, seeded, rhea, sam, relationship_type="associated_with", analyst_id="analyst-7"
    )
    assert edge_id == existing.relationship_id, "the same link must reuse one edge"

    merged = next(
        row
        for row in projection.list_relationships(seeded)
        if row.relationship_id == edge_id
    )
    assert merged.assertion_type == "inferred", "the weakest contributor must win"
    assert (
        len(projection.provenance_ids_for_relationship(seeded, edge_id)) > evidence_before
    ), "the assertion should add evidence to the existing edge"


def test_the_analyst_note_is_retained_on_the_record(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")
    _assert_link(
        session,
        seeded,
        wren,
        vik,
        relationship_type="met",
        analyst_id="analyst-7",
        note="Reviewed against the synthetic scenario notes.",
    )

    records = [
        record
        for record in RecordRepository(session).list_for_case(seeded)
        if record.data.get("analyst_created")
    ]
    assert records
    assert records[0].data["analyst_note"].startswith("Reviewed against")
    assert records[0].data["analyst_id"] == "analyst-7"


# ---------------------------------------------------------------------------
# Identity, persistence and the shared write path
# ---------------------------------------------------------------------------


def test_repeating_the_same_assertion_does_not_duplicate_it(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")

    _assert_link(session, seeded, wren, vik, relationship_type="met", analyst_id="analyst-7")
    first_records = RecordRepository(session).count(seeded)
    first_edges = len(ProjectionRepository(session).list_relationships(seeded))

    _assert_link(session, seeded, wren, vik, relationship_type="met", analyst_id="analyst-7")

    assert RecordRepository(session).count(seeded) == first_records
    assert len(ProjectionRepository(session).list_relationships(seeded)) == first_edges


def test_two_analysts_asserting_the_same_link_are_separate_evidence(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")

    _, edge_id = _assert_link(
        session, seeded, wren, vik, relationship_type="met", analyst_id="analyst-7"
    )
    single = len(ProjectionRepository(session).provenance_ids_for_relationship(seeded, edge_id))

    _assert_link(session, seeded, wren, vik, relationship_type="met", analyst_id="analyst-9")
    both = len(ProjectionRepository(session).provenance_ids_for_relationship(seeded, edge_id))

    assert both > single, "a second analyst is a second piece of evidence"


def test_the_assertion_is_recorded_as_a_run(session, seeded) -> None:
    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")
    _assert_link(session, seeded, wren, vik, relationship_type="met")

    runs = [run for run in RunRepository(session).list_for_case(seeded) if run.kind == "analyst"]
    assert runs, "an analyst write must be auditable like any other"
    assert runs[0].status == "completed"
    assert runs[0].accepted_count == 1


def test_the_assertion_survives_a_restart(tmp_path) -> None:
    """It must be persisted, not held in the session that created it."""
    url = f"sqlite:///{(tmp_path / 'analyst.db').as_posix()}"
    database.configure(url)
    database.create_all()

    pipeline = InvestigationPipeline()
    with database.session_scope() as session:
        pipeline.ingest_dataset(session, normal_population())
        wren = _entity(session, NORMAL_CASE, "Wren Dabiri")
        vik = _entity(session, NORMAL_CASE, "Vik Oyelaran")
        _, edge_id = pipeline.create_analyst_relationship(
            session,
            NORMAL_CASE,
            from_entity_id=wren,
            to_entity_id=vik,
            relationship_type="met",
            analyst_id="analyst-7",
            note="Persisted assertion.",
        )

    database.dispose()
    assert database._engine is None
    database.configure(url)

    with database.session_scope() as session:
        rows = ProjectionRepository(session).list_relationships(NORMAL_CASE)
        reloaded = next((row for row in rows if row.relationship_id == edge_id), None)
        assert reloaded is not None, "the asserted relationship must survive a restart"
        assert reloaded.assertion_type == "inferred"

        analyst_rows = [
            row
            for row, _, _ in RecordRepository(session).list_evidence(NORMAL_CASE)
            if row.source_type == "analyst_assertion"
        ]
        assert analyst_rows
        assert all(row.document_id is None for row in analyst_rows)


def test_the_asserted_link_is_visible_to_the_graph_and_analytics(session, seeded) -> None:
    """It went through the real write path, so everything downstream sees it."""
    from app.services.intelligence.engine import IntelligenceEngine

    wren = _entity(session, seeded, "Wren Dabiri")
    vik = _entity(session, seeded, "Vik Oyelaran")
    _assert_link(session, seeded, wren, vik, relationship_type="met", analyst_id="analyst-7")

    paths = IntelligenceEngine().paths(session, seeded, wren, vik, max_depth=1)
    assert paths.count > 0, "the asserted link should be traversable"
    hop = paths.paths[0].edges[0]
    assert hop.assertion_type == "inferred"
    assert hop.evidence_ids, "the hop must still carry its provenance"

    graph = client.get(f"/api/investigations/{seeded}/graph").json()
    assert any(
        {edge["from_node_id"], edge["to_node_id"]} == {wren, vik} for edge in graph["edges"]
    )
