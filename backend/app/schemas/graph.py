"""Entity-resolution and knowledge-graph contracts.

Every element in this module is scoped to exactly one investigation. A graph may
never mix ``case_id`` values, because doing so would let evidence from one
investigation appear to corroborate another.

Resolution uncertainty is carried all the way onto the graph node. A node that
came from an ambiguous match keeps its ``match_status``, ``match_confidence``
and ``review_candidates`` so a reviewer can always tell a confident identity
from one still awaiting adjudication.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.investigation import (
    CASE_ID_PATTERN,
    AssertionType,
    EntityType,
    IngestedRecord,
    ProvenanceRecord,
    RelationshipType,
    StrictModel,
)


MatchStatus = Literal["canonical", "exact_match", "candidate_review"]
GraphElementType = Literal["node", "edge"]


class ResolvedEntity(StrictModel):
    """One entity identity within one case.

    ``canonical_id`` is minted from ``(case_id, entity_type, normalized_value)``
    so it is stable regardless of the order records arrive in, and can never
    collide with the same description in another case.
    """

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    canonical_id: str
    entity_type: EntityType
    attributes: dict
    source_entity_ids: list[str] = Field(min_length=1)
    provenance: list[ProvenanceRecord] = Field(min_length=1)
    match_confidence: float = Field(ge=0, le=1)
    match_status: MatchStatus
    assertion_type: AssertionType = "observed"
    review_candidates: list[str] = Field(default_factory=list)


class EntityResolutionResult(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    entities: list[ResolvedEntity]
    unresolved_record_ids: list[str] = Field(default_factory=list)


class KnowledgeGraphNode(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    node_id: str
    entity_type: EntityType
    attributes: dict
    source_entity_ids: list[str] = Field(min_length=1)
    provenance: list[ProvenanceRecord] = Field(min_length=1)
    match_confidence: float = Field(ge=0, le=1)
    match_status: MatchStatus
    assertion_type: AssertionType = "observed"
    review_candidates: list[str] = Field(default_factory=list)


class KnowledgeGraphEdge(StrictModel):
    """A canonical relationship between two nodes that both exist in this graph.

    Edge identity is ``(case_id, from, to, relationship_type)``. Several source
    records asserting the same relationship contribute provenance to one edge
    rather than producing duplicate edges, so evidence lookup returns every
    supporting record.

    ``confidence`` is the highest confidence among contributing records, and
    ``assertion_type`` the weakest, so an edge never presents itself as better
    evidenced than its weakest contributing claim.
    """

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    edge_id: str
    from_node_id: str
    to_node_id: str
    relationship_type: RelationshipType
    source_record_ids: list[str] = Field(min_length=1)
    observed_at: datetime | None = None
    occurred_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    provenance: list[ProvenanceRecord] = Field(min_length=1)
    assertion_type: AssertionType = "observed"


class RejectedEdge(StrictModel):
    """A relationship that was deliberately not turned into an edge.

    Recorded rather than dropped silently, so an absent edge is always
    explainable instead of merely missing.
    """

    record_id: str
    reason: str


class KnowledgeGraph(StrictModel):
    graph_id: str = Field(pattern=r"^graph_[a-z0-9-]+$")
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    edges: list[KnowledgeGraphEdge] = Field(default_factory=list)
    unresolved_record_ids: list[str] = Field(default_factory=list)
    rejected_edges: list[RejectedEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_integrity(self) -> "KnowledgeGraph":
        node_ids: set[str] = set()
        for node in self.nodes:
            if node.case_id != self.case_id:
                raise ValueError(f"node '{node.node_id}' belongs to case '{node.case_id}'")
            if node.node_id in node_ids:
                raise ValueError(f"duplicate node_id '{node.node_id}'")
            node_ids.add(node.node_id)

        edge_ids: set[str] = set()
        for edge in self.edges:
            if edge.case_id != self.case_id:
                raise ValueError(f"edge '{edge.edge_id}' belongs to case '{edge.case_id}'")
            if edge.edge_id in edge_ids:
                raise ValueError(f"duplicate edge_id '{edge.edge_id}'")
            edge_ids.add(edge.edge_id)
            for endpoint in (edge.from_node_id, edge.to_node_id):
                if endpoint not in node_ids:
                    raise ValueError(
                        f"edge '{edge.edge_id}' references node '{endpoint}' that is not in the graph"
                    )
        return self


class ResolutionRequest(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    records: list[IngestedRecord] = Field(min_length=1)


class GraphBuildRequest(ResolutionRequest):
    graph_id: str = Field(pattern=r"^graph_[a-z0-9-]+$")


class EvidenceResponse(StrictModel):
    """Every piece of provenance held by every element matching ``element_id``."""

    element_id: str
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    element_types: list[GraphElementType] = Field(default_factory=list)
    evidence: list[ProvenanceRecord] = Field(default_factory=list)
