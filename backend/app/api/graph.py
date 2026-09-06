from fastapi import APIRouter, HTTPException

from app.api.dependencies import graph_service, graph_store, resolver
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
    try:
        return resolver.resolve(request.case_id, request.records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", response_model=KnowledgeGraph)
def build_graph(request: GraphBuildRequest) -> KnowledgeGraph:
    try:
        graph = graph_service.build(request.graph_id, request.case_id, request.records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    graph_store.put(graph, request.records)
    return graph


@router.get("/{graph_id}", response_model=KnowledgeGraph)
def get_graph(graph_id: str) -> KnowledgeGraph:
    graph = graph_store.get(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="knowledge graph not found")
    return graph


@router.get("/{graph_id}/evidence/{element_id}", response_model=EvidenceResponse)
def get_evidence(graph_id: str, element_id: str) -> EvidenceResponse:
    graph = get_graph(graph_id)
    element_types, evidence = graph_service.evidence_for(graph, element_id)
    if not element_types:
        raise HTTPException(status_code=404, detail="graph element not found")
    return EvidenceResponse(
        element_id=element_id,
        case_id=graph.case_id,
        element_types=element_types,  # type: ignore[arg-type]
        evidence=evidence,
    )
