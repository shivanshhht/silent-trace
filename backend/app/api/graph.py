from fastapi import APIRouter, HTTPException

from app.schemas.graph import (
    EntityResolutionResult,
    EvidenceResponse,
    GraphBuildRequest,
    KnowledgeGraph,
    ResolutionRequest,
)
from app.services.entity_resolution import EntityResolutionService
from app.services.knowledge_graph import KnowledgeGraphService

router = APIRouter(prefix="/api/graph", tags=["graph"])
_resolver = EntityResolutionService()
_graph_service = KnowledgeGraphService(_resolver)
_graphs: dict[str, KnowledgeGraph] = {}


@router.post("/resolve", response_model=EntityResolutionResult)
def resolve_entities(request: ResolutionRequest) -> EntityResolutionResult:
    return _resolver.resolve(request.records)


@router.post("", response_model=KnowledgeGraph)
def build_graph(request: GraphBuildRequest) -> KnowledgeGraph:
    graph = _graph_service.build(request.graph_id, request.records)
    _graphs[graph.graph_id] = graph
    return graph


@router.get("/{graph_id}", response_model=KnowledgeGraph)
def get_graph(graph_id: str) -> KnowledgeGraph:
    if graph_id not in _graphs:
        raise HTTPException(status_code=404, detail="knowledge graph not found")
    return _graphs[graph_id]


@router.get("/{graph_id}/evidence/{element_id}", response_model=EvidenceResponse)
def get_evidence(graph_id: str, element_id: str) -> EvidenceResponse:
    graph = get_graph(graph_id)
    for node in graph.nodes:
        if node.node_id == element_id:
            return EvidenceResponse(element_id=element_id, evidence=node.provenance)
    for edge in graph.edges:
        if edge.edge_id == element_id:
            return EvidenceResponse(element_id=element_id, evidence=edge.provenance)
    raise HTTPException(status_code=404, detail="graph element not found")
