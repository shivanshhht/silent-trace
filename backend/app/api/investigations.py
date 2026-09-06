"""Persistence-backed investigation API.

Every route is addressed by ``case_id`` and reads only through case-scoped
repository methods. A case that does not exist is a 404; a case that exists but
holds no data yet is an empty collection, not a 404, because "this
investigation has no entities" and "there is no such investigation" are
different answers and a caller must be able to tell them apart.
"""

from fastapi import APIRouter, HTTPException

from app.api.dependencies import SessionDep, pipeline
from app.db.models import InvestigationCase
from app.db.repositories import (
    CaseRepository,
    DocumentRepository,
    GraphRepository,
    ProjectionRepository,
    RecordRepository,
    RunRepository,
)
from app.schemas.graph import KnowledgeGraph
from app.schemas.persistence import (
    CreateInvestigationRequest,
    CreateRelationshipRequest,
    DocumentListResponse,
    EntityListResponse,
    EvidenceListResponse,
    InvestigationListResponse,
    InvestigationSummary,
    PersistedDocument,
    PersistedEntity,
    PersistedEvidence,
    PersistedRelationship,
    PersistedRun,
    RelationshipListResponse,
    RunListResponse,
)
from app.services.identity import mint_edge_id
from app.services.pipeline import default_graph_id

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


def _require_case(session, case_id: str) -> InvestigationCase:
    case = CaseRepository(session).get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"investigation '{case_id}' not found")
    return case


def _summary(session, case: InvestigationCase) -> InvestigationSummary:
    case_id = case.case_id
    projection = ProjectionRepository(session)
    graph = GraphRepository(session).current_for_case(case_id)
    return InvestigationSummary(
        case_id=case_id,
        title=case.title,
        description=case.description,
        status=case.status,
        created_at=case.created_at,
        updated_at=case.updated_at,
        document_count=len(DocumentRepository(session).list_for_case(case_id)),
        run_count=len(RunRepository(session).list_for_case(case_id)),
        record_count=RecordRepository(session).count(case_id),
        entity_count=len(projection.list_entities(case_id)),
        relationship_count=len(projection.list_relationships(case_id)),
        graph_id=graph.graph_id if graph is not None else None,
    )


@router.get("", response_model=InvestigationListResponse)
def list_investigations(session: SessionDep) -> InvestigationListResponse:
    cases = CaseRepository(session).list_all()
    summaries = [_summary(session, case) for case in cases]
    return InvestigationListResponse(investigations=summaries, count=len(summaries))


@router.post("", response_model=InvestigationSummary, status_code=201)
def create_investigation(
    request: CreateInvestigationRequest, session: SessionDep
) -> InvestigationSummary:
    cases = CaseRepository(session)
    if cases.get(request.case_id) is not None:
        raise HTTPException(
            status_code=409, detail=f"investigation '{request.case_id}' already exists"
        )
    case = cases.create(request.case_id, request.title, request.description, request.status)
    session.commit()
    return _summary(session, case)


@router.get("/{case_id}", response_model=InvestigationSummary)
def get_investigation(case_id: str, session: SessionDep) -> InvestigationSummary:
    return _summary(session, _require_case(session, case_id))


@router.get("/{case_id}/entities", response_model=EntityListResponse)
def get_entities(case_id: str, session: SessionDep) -> EntityListResponse:
    _require_case(session, case_id)
    projection = ProjectionRepository(session)
    entities = [
        PersistedEntity(
            case_id=row.case_id,
            canonical_id=row.canonical_id,
            entity_type=row.entity_type,
            canonical_value=row.canonical_value,
            attributes=row.attributes,
            source_entity_ids=row.source_entity_ids,
            match_status=row.match_status,
            match_confidence=row.match_confidence,
            assertion_type=row.assertion_type,
            review_candidates=row.review_candidates,
            evidence_count=len(projection.provenance_ids_for_entity(case_id, row.canonical_id)),
        )
        for row in projection.list_entities(case_id)
    ]
    return EntityListResponse(case_id=case_id, entities=entities, count=len(entities))


def _analyst_provenance_ids(session, case_id: str) -> set[str]:
    """Provenance rows that record an analyst assertion rather than a document."""
    return {
        row.provenance_id
        for row, _, _ in RecordRepository(session).list_evidence(case_id)
        if row.source_type == "analyst_assertion"
    }


def _persisted_relationship(
    session, case_id: str, row, analyst_ids: set[str]
) -> PersistedRelationship:
    evidence_ids = ProjectionRepository(session).provenance_ids_for_relationship(
        case_id, row.relationship_id
    )
    return PersistedRelationship(
        case_id=row.case_id,
        relationship_id=row.relationship_id,
        from_entity_id=row.from_entity_id,
        to_entity_id=row.to_entity_id,
        relationship_type=row.relationship_type,
        assertion_type=row.assertion_type,
        confidence=row.confidence,
        source_record_ids=row.source_record_ids,
        observed_at=row.observed_at,
        occurred_at=row.occurred_at,
        evidence_count=len(evidence_ids),
        analyst_created=bool(set(evidence_ids) & analyst_ids),
    )


@router.get("/{case_id}/relationships", response_model=RelationshipListResponse)
def get_relationships(case_id: str, session: SessionDep) -> RelationshipListResponse:
    _require_case(session, case_id)
    analyst_ids = _analyst_provenance_ids(session, case_id)
    relationships = [
        _persisted_relationship(session, case_id, row, analyst_ids)
        for row in ProjectionRepository(session).list_relationships(case_id)
    ]
    return RelationshipListResponse(
        case_id=case_id, relationships=relationships, count=len(relationships)
    )


@router.post(
    "/{case_id}/relationships", response_model=PersistedRelationship, status_code=201
)
def create_analyst_relationship(
    case_id: str, request: CreateRelationshipRequest, session: SessionDep
) -> PersistedRelationship:
    """Record a link a human analyst asserts between two entities in this case.

    The assertion goes through the same pipeline as every other write, so it is
    resolved, projected and evidenced identically. It is stored as an
    ``inferred`` claim whose provenance names the assertion itself rather than
    any document, because no document exists.

    If a source already asserts the same link, Stage A edge identity pools both
    onto one edge and keeps the weakest assertion, so an analyst opinion adds
    evidence without ever promoting a relationship to observed.
    """
    _require_case(session, case_id)
    try:
        pipeline.create_analyst_relationship(
            session,
            case_id,
            from_entity_id=request.from_entity_id,
            to_entity_id=request.to_entity_id,
            relationship_type=request.relationship_type,
            confidence=request.confidence,
            context=request.context,
            analyst_id=request.analyst_id,
            note=request.note,
            occurred_at=request.occurred_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    edge_id = mint_edge_id(
        case_id, request.relationship_type, request.from_entity_id, request.to_entity_id
    )
    row = next(
        (
            candidate
            for candidate in ProjectionRepository(session).list_relationships(case_id)
            if candidate.relationship_id == edge_id
        ),
        None,
    )
    if row is None:
        raise HTTPException(
            status_code=500, detail="the asserted relationship did not reach the graph"
        )
    return _persisted_relationship(
        session, case_id, row, _analyst_provenance_ids(session, case_id)
    )


@router.get("/{case_id}/evidence", response_model=EvidenceListResponse)
def get_evidence(case_id: str, session: SessionDep) -> EvidenceListResponse:
    _require_case(session, case_id)
    evidence = [
        PersistedEvidence(
            case_id=row.case_id,
            provenance_id=row.provenance_id,
            record_id=row.record_id,
            record_type=record_type,
            source_record_id=row.source_record_id,
            document_id=row.document_id,
            provenance_type=row.provenance_type,
            assertion_type=assertion_type,
            content_hash=row.content_hash,
            source_type=row.source_type,
            extraction_run_id=row.extraction_run_id,
            character_start=row.character_start,
            character_end=row.character_end,
            snippet=row.snippet,
            observed_at=row.observed_at,
        )
        for row, record_type, assertion_type in RecordRepository(session).list_evidence(case_id)
    ]
    return EvidenceListResponse(case_id=case_id, evidence=evidence, count=len(evidence))


@router.get("/{case_id}/documents", response_model=DocumentListResponse)
def get_documents(case_id: str, session: SessionDep) -> DocumentListResponse:
    """The source documents this case holds.

    Read-only, and derived from nothing: every field is the stored row. This is
    what lets a piece of evidence naming a ``document_id`` be followed to the
    document it came from instead of dead-ending at the identifier.
    """
    _require_case(session, case_id)
    documents = [
        PersistedDocument(
            case_id=row.case_id,
            document_id=row.document_id,
            source_type=row.source_type,
            title=row.title,
            content_hash=row.content_hash,
            content=row.content,
            reliability=row.reliability,
            collected_at=row.collected_at,
        )
        for row in DocumentRepository(session).list_for_case(case_id)
    ]
    return DocumentListResponse(case_id=case_id, documents=documents, count=len(documents))


@router.get("/{case_id}/runs", response_model=RunListResponse)
def get_runs(case_id: str, session: SessionDep) -> RunListResponse:
    """The ingestion and extraction runs recorded for this case."""
    _require_case(session, case_id)
    runs = [
        PersistedRun(
            case_id=row.case_id,
            run_id=row.run_id,
            kind=row.kind,
            status=row.status,
            document_id=row.document_id,
            dataset_id=row.dataset_id,
            graph_id=row.graph_id,
            accepted_count=row.accepted_count,
            rejected_count=row.rejected_count,
            errors=list(row.errors or []),
            started_at=row.started_at,
            completed_at=row.completed_at,
        )
        for row in RunRepository(session).list_for_case(case_id)
    ]
    return RunListResponse(case_id=case_id, runs=runs, count=len(runs))


@router.get("/{case_id}/graph", response_model=KnowledgeGraph)
def get_case_graph(case_id: str, session: SessionDep) -> KnowledgeGraph:
    """The current graph for a case.

    A case with no records yet returns an empty graph rather than a 404: the
    investigation exists, and its graph is genuinely empty.
    """
    _require_case(session, case_id)
    graph = GraphRepository(session).current_for_case(case_id)
    if graph is None:
        return KnowledgeGraph(graph_id=default_graph_id(case_id), case_id=case_id)
    return graph
