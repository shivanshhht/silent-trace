from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.investigation import EntityType, IngestedRecord, StrictModel


MatchStatus = Literal["canonical", "exact_match", "candidate_review"]
GraphElementType = Literal["node", "edge"]


class EvidenceReference(StrictModel):
    source_record_id: str = Field(pattern=r"^src_[a-z0-9-]+$")
    record_id: str
    observed_at: datetime | None = None
    evidence_type: Literal["observed", "resolved_association"] = "observed"


class ResolvedEntity(StrictModel):
    canonical_id: str
    entity_type: EntityType
    attributes: dict
    source_entity_ids: list[str] = Field(min_length=1)
    provenance: list[EvidenceReference] = Field(min_length=1)
    match_confidence: float = Field(ge=0, le=1)
    match_status: MatchStatus
    review_candidates: list[str] = Field(default_factory=list)


class EntityResolutionResult(StrictModel):
    entities: list[ResolvedEntity]
    unresolved_record_ids: list[str] = Field(default_factory=list)


class KnowledgeGraphNode(StrictModel):
    node_id: str
    entity_type: EntityType
    attributes: dict
    source_entity_ids: list[str] = Field(min_length=1)
    provenance: list[EvidenceReference] = Field(min_length=1)


class KnowledgeGraphEdge(StrictModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    relationship_type: str
    source_record_id: str
    observed_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    provenance: list[EvidenceReference] = Field(min_length=1)
    evidence_type: Literal["observed", "resolved_association"] = "observed"


class KnowledgeGraph(StrictModel):
    graph_id: str
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]


class ResolutionRequest(StrictModel):
    records: list[IngestedRecord] = Field(min_length=1)


class GraphBuildRequest(ResolutionRequest):
    graph_id: str = Field(pattern=r"^graph_[a-z0-9-]+$")


class EvidenceResponse(StrictModel):
    element_id: str
    evidence: list[EvidenceReference]
