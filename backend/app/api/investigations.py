"""Persistence-backed investigation API.

Every route is addressed by ``case_id`` and reads only through case-scoped
repository methods. A case that does not exist is a 404; a case that exists but
holds no data yet is an empty collection, not a 404, because "this
investigation has no entities" and "there is no such investigation" are
different answers and a caller must be able to tell them apart.
"""

from fastapi import APIRouter, HTTPException

from app.api.dependencies import SessionDep
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
    EntityListResponse,
    EvidenceListResponse,
    InvestigationListResponse,
    InvestigationSummary,
    PersistedEntity,
    PersistedEvidence,
    PersistedRelationship,
    RelationshipListResponse,
)
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


@router.get("/{case_id}/relationships", response_model=RelationshipListResponse)
def get_relationships(case_id: str, session: SessionDep) -> RelationshipListResponse:
    _require_case(session, case_id)
    projection = ProjectionRepository(session)
    relationships = [
        PersistedRelationship(
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
            evidence_count=len(
                projection.provenance_ids_for_relationship(case_id, row.relationship_id)
            ),
        )
        for row in projection.list_relationships(case_id)
    ]
    return RelationshipListResponse(
        case_id=case_id, relationships=relationships, count=len(relationships)
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
