from fastapi import APIRouter, HTTPException

from app.api.dependencies import SessionDep, graph_service, pipeline, resolver
from app.db.repositories import GraphRepository
from app.schemas.graph import (
    EntityResolutionResult,
    EvidenceResponse,
    GraphBuildRequest,
    KnowledgeGraph,
    ResolutionRequest,
)

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.post("/resolve", response_model=EntityResolutionResult)
def resolve_entities(request: ResolutionRequest) -> EntityResolutionResult:
    """Resolution on its own is a pure function of the records supplied.

    It writes nothing, so it stays available as a way to preview how a record
    set would resolve without committing it to an investigation.
    """
    try:
        return resolver.resolve(request.case_id, request.records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", response_model=KnowledgeGraph)
def build_graph(request: GraphBuildRequest, session: SessionDep) -> KnowledgeGraph:
    try:
        return pipeline.build_graph(session, request.graph_id, request.case_id, request.records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{graph_id}", response_model=KnowledgeGraph)
def get_graph(graph_id: str, session: SessionDep) -> KnowledgeGraph:
    graph = GraphRepository(session).current(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="knowledge graph not found")
    return graph


@router.get("/{graph_id}/evidence/{element_id}", response_model=EvidenceResponse)
def get_evidence(graph_id: str, element_id: str, session: SessionDep) -> EvidenceResponse:
    graph = get_graph(graph_id, session)
    element_types, evidence = graph_service.evidence_for(graph, element_id)
    if not element_types:
        raise HTTPException(status_code=404, detail="graph element not found")
    return EvidenceResponse(
        element_id=element_id,
        case_id=graph.case_id,
        element_types=element_types,  # type: ignore[arg-type]
        evidence=evidence,
    )
