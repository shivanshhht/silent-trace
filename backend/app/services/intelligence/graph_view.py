"""A read-only analysis projection over the persisted investigation.

This is **not** a second graph implementation. Stage B already owns the graph:
entities and relationships are rows written by the one pipeline, and this module
only loads them for one case and indexes them for traversal. Nothing here
writes, and nothing here can produce a node or an edge that the persisted
projection does not already contain.

Two modelling assumptions are made explicit because every metric downstream
inherits them:

* **Structure is treated as undirected.** ``transacted_with`` and ``contacted``
  have a direction, and the direction is preserved on every edge and reported in
  paths. For centrality and community structure, though, the question is who is
  reachable through whom, so adjacency is symmetric. A one-way payment still
  connects two people.

* **Parallel edges are kept.** Two entities may be linked by several
  relationship types at once (they spoke, and they transacted). Those stay
  distinct edges, because collapsing them would erase the evidence that
  distinguishes a single contact from a sustained pattern.
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.db.repositories import ProjectionRepository, RecordRepository
from app.schemas.investigation import ProvenanceRecord


# Relationship type -> structural context, used only when the source document
# did not state a context of its own. Derived contexts are always reported as
# ``inferred``; a stated one is ``observed``.
DERIVED_CONTEXT: dict[str, str] = {
    "contacted": "communication",
    "transacted_with": "financial",
    "located_at": "geographic",
    "met": "operational",
    "owns": "operational",
    "uses": "operational",
    "involved_in": "operational",
    "member_of": "community",
    # ``associated_with`` deliberately stays unknown. It is the vocabulary entry
    # used when a source asserts a link without saying what kind, and guessing a
    # setting for it would manufacture context that no document supports.
    "associated_with": "unknown",
}

BUSINESS_ORGANIZATION_WORDS = {
    "company",
    "corporation",
    "business",
    "employer",
    "firm",
    "logistics",
    "contractor",
}


def entity_label(entity_type: str, attributes: dict) -> str:
    """A short human label for an entity, taken only from stated attributes."""
    if entity_type == "person":
        return attributes.get("display_name") or attributes.get("entity_id") or "unnamed person"
    if entity_type == "phone":
        return attributes.get("number") or "unknown number"
    if entity_type == "vehicle":
        return attributes.get("registration") or "unknown vehicle"
    if entity_type == "location":
        label = attributes.get("label") or "unknown location"
        locality = attributes.get("locality")
        return f"{label} ({locality})" if locality else label
    if entity_type == "organization":
        return attributes.get("name") or "unnamed organization"
    if entity_type == "incident":
        summary = attributes.get("summary") or "unspecified incident"
        return summary if len(summary) <= 80 else f"{summary[:77]}..."
    return attributes.get("entity_id") or "unknown entity"


@dataclass(frozen=True)
class AnalysisEntity:
    entity_id: str
    entity_type: str
    label: str
    attributes: dict
    assertion_type: str
    match_status: str
    match_confidence: float
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisEdge:
    relationship_id: str
    source: str
    target: str
    relationship_type: str
    context: str
    context_assertion: str
    assertion_type: str
    confidence: float
    observed_at: datetime | None
    occurred_at: datetime | None
    source_record_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()

    @property
    def interaction_count(self) -> int:
        """How many distinct source records assert this relationship."""
        return max(1, len(self.source_record_ids))

    @property
    def timestamp(self) -> datetime | None:
        """When the relationship happened, falling back to when it was recorded."""
        return self.occurred_at or self.observed_at

    def other_end(self, entity_id: str) -> str:
        return self.target if entity_id == self.source else self.source


@dataclass
class CaseGraphView:
    """One investigation, indexed for traversal. Read-only."""

    case_id: str
    entities: dict[str, AnalysisEntity] = field(default_factory=dict)
    edges: list[AnalysisEdge] = field(default_factory=list)
    records: dict[str, dict] = field(default_factory=dict)
    provenance: dict[str, ProvenanceRecord] = field(default_factory=dict)
    _adjacency: dict[str, list[AnalysisEdge]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        adjacency: dict[str, list[AnalysisEdge]] = {node: [] for node in self.entities}
        for edge in self.edges:
            adjacency.setdefault(edge.source, []).append(edge)
            adjacency.setdefault(edge.target, []).append(edge)
        self._adjacency = adjacency

    # -- basic accessors -------------------------------------------------

    @property
    def node_ids(self) -> list[str]:
        """Deterministic node ordering. Every algorithm here iterates in this order."""
        return sorted(self.entities)

    @property
    def node_count(self) -> int:
        return len(self.entities)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def label(self, entity_id: str) -> str:
        entity = self.entities.get(entity_id)
        return entity.label if entity else entity_id

    def entity_type(self, entity_id: str) -> str:
        entity = self.entities.get(entity_id)
        return entity.entity_type if entity else "person"

    def incident_edges(self, entity_id: str) -> list[AnalysisEdge]:
        return list(self._adjacency.get(entity_id, ()))

    def neighbours(self, entity_id: str) -> list[str]:
        seen = {edge.other_end(entity_id) for edge in self.incident_edges(entity_id)}
        seen.discard(entity_id)
        return sorted(seen)

    def edges_between(self, first: str, second: str) -> list[AnalysisEdge]:
        return [
            edge
            for edge in self.incident_edges(first)
            if edge.other_end(first) == second
        ]

    def degree(self, entity_id: str) -> int:
        return len(self.neighbours(entity_id))

    def weighted_degree(self, entity_id: str) -> float:
        """Degree weighted by how many source records support each link.

        A single recorded contact and forty recorded contacts are structurally
        different, and plain degree cannot tell them apart.
        """
        return float(sum(edge.interaction_count for edge in self.incident_edges(entity_id)))

    def edges_of_type(self, relationship_type: str) -> list[AnalysisEdge]:
        return [edge for edge in self.edges if edge.relationship_type == relationship_type]

    def timestamps(self) -> list[datetime]:
        return sorted(edge.timestamp for edge in self.edges if edge.timestamp is not None)

    def evidence_for_edges(self, edges: list[AnalysisEdge]) -> list[str]:
        collected: list[str] = []
        for edge in edges:
            for evidence_id in edge.evidence_ids:
                if evidence_id not in collected:
                    collected.append(evidence_id)
        return collected


def _resolve_context(
    edge_type: str, source_record_ids: tuple[str, ...], records: dict[str, dict], organization_type: str | None
) -> tuple[str, str]:
    """Return ``(context, assertion)`` for one relationship.

    A context stated by the source is ``observed``. Anything else is derived
    from the relationship type and reported as ``inferred``, so a reader can
    always tell a documented setting from a structural guess.
    """
    for record_id in source_record_ids:
        data = records.get(record_id) or {}
        stated = data.get("context")
        if stated:
            return stated, "observed"

    derived = DERIVED_CONTEXT.get(edge_type, "unknown")
    if derived == "community" and organization_type:
        lowered = organization_type.lower()
        if any(word in lowered for word in BUSINESS_ORGANIZATION_WORDS):
            return "business", "inferred"
    return derived, "inferred"


def build_case_graph_view(session, case_id: str) -> CaseGraphView:
    """Load one case from the persisted projection into an analysis view."""
    projection = ProjectionRepository(session)
    record_repository = RecordRepository(session)

    entity_rows = projection.list_entities(case_id)
    relationship_rows = projection.list_relationships(case_id)

    records = {
        record.record_id: record.data for record in record_repository.list_for_case(case_id)
    }
    provenance = {
        row.provenance_id: RecordRepository.to_schema(row)
        for row, _, _ in record_repository.list_evidence(case_id)
    }

    entities: dict[str, AnalysisEntity] = {}
    for row in entity_rows:
        entities[row.canonical_id] = AnalysisEntity(
            entity_id=row.canonical_id,
            entity_type=row.entity_type,
            label=entity_label(row.entity_type, row.attributes),
            attributes=row.attributes,
            assertion_type=row.assertion_type,
            match_status=row.match_status,
            match_confidence=row.match_confidence,
            evidence_ids=tuple(projection.provenance_ids_for_entity(case_id, row.canonical_id)),
        )

    edges: list[AnalysisEdge] = []
    for row in relationship_rows:
        evidence_ids = tuple(
            projection.provenance_ids_for_relationship(case_id, row.relationship_id)
        )
        document_ids: list[str] = []
        for evidence_id in evidence_ids:
            item = provenance.get(evidence_id)
            if item and item.document_id and item.document_id not in document_ids:
                document_ids.append(item.document_id)

        organization_type = None
        for endpoint in (row.from_entity_id, row.to_entity_id):
            entity = entities.get(endpoint)
            if entity and entity.entity_type == "organization":
                organization_type = entity.attributes.get("organization_type")

        context, context_assertion = _resolve_context(
            row.relationship_type,
            tuple(row.source_record_ids or ()),
            records,
            organization_type,
        )

        edges.append(
            AnalysisEdge(
                relationship_id=row.relationship_id,
                source=row.from_entity_id,
                target=row.to_entity_id,
                relationship_type=row.relationship_type,
                context=context,
                context_assertion=context_assertion,
                assertion_type=row.assertion_type,
                confidence=row.confidence,
                observed_at=row.observed_at,
                occurred_at=row.occurred_at,
                source_record_ids=tuple(row.source_record_ids or ()),
                evidence_ids=evidence_ids,
                document_ids=tuple(document_ids),
            )
        )

    return CaseGraphView(
        case_id=case_id,
        entities=entities,
        edges=edges,
        records=records,
        provenance=provenance,
    )
