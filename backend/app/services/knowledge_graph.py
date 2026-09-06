"""Knowledge-graph construction for a single investigation.

Construction is total and explainable: every relational record either becomes an
edge or appears in ``rejected_edges`` with a reason. Nothing is dropped quietly.

An edge is only created when both endpoints resolve to nodes that exist in this
graph. An assertion whose endpoints cannot be resolved is not a weaker edge, it
is not an edge at all, because a dangling endpoint would let the graph claim a
connection it cannot evidence.
"""

from datetime import datetime

from app.schemas.graph import (
    KnowledgeGraph,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    RejectedEdge,
)
from app.schemas.investigation import (
    RECORD_TYPE_RELATIONSHIP,
    IngestedRecord,
    ProvenanceRecord,
    weakest_assertion,
)
from app.services.entity_resolution import EntityResolutionService
from app.services.identity import mint_edge_id


RELATIONAL_RECORD_TYPES = {"communication", "financial_transaction", "relationship"}


def _earliest(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return min(current, candidate)


class KnowledgeGraphService:
    def __init__(self, resolver: EntityResolutionService | None = None) -> None:
        self.resolver = resolver or EntityResolutionService()

    def build(self, graph_id: str, case_id: str, records: list[IngestedRecord]) -> KnowledgeGraph:
        foreign = sorted({record.case_id for record in records} - {case_id})
        if foreign:
            raise ValueError(
                f"cannot build graph '{graph_id}' for case '{case_id}': "
                f"records also reference {foreign}"
            )

        resolution = self.resolver.resolve(case_id, records)

        nodes = [
            KnowledgeGraphNode(
                case_id=case_id,
                node_id=entity.canonical_id,
                entity_type=entity.entity_type,
                attributes=entity.attributes,
                source_entity_ids=entity.source_entity_ids,
                provenance=entity.provenance,
                match_confidence=entity.match_confidence,
                match_status=entity.match_status,
                assertion_type=entity.assertion_type,
                review_candidates=entity.review_candidates,
            )
            for entity in resolution.entities
        ]

        # One pass to index source ids onto their canonical node.
        canonical_by_source: dict[str, str] = {
            source_id: node.node_id
            for node in nodes
            for source_id in node.source_entity_ids
        }

        edges: dict[str, KnowledgeGraphEdge] = {}
        rejected: list[RejectedEdge] = []

        for record in records:
            if record.record_type not in RELATIONAL_RECORD_TYPES:
                continue
            data = record.data
            relationship_type = data.get("relationship_type") or RECORD_TYPE_RELATIONSHIP.get(
                record.record_type
            )
            if relationship_type is None:
                rejected.append(
                    RejectedEdge(
                        record_id=record.record_id,
                        reason=f"no canonical relationship type for record type '{record.record_type}'",
                    )
                )
                continue

            source_id = data.get("from_entity_id")
            target_id = data.get("to_entity_id")
            missing = [
                str(endpoint)
                for endpoint in (source_id, target_id)
                if not endpoint or endpoint not in canonical_by_source
            ]
            if missing:
                rejected.append(
                    RejectedEdge(
                        record_id=record.record_id,
                        reason=(
                            f"endpoint(s) {missing} did not resolve to an entity in case "
                            f"'{case_id}'; no edge was created"
                        ),
                    )
                )
                continue

            from_node_id = canonical_by_source[source_id]
            to_node_id = canonical_by_source[target_id]
            edge_id = mint_edge_id(case_id, relationship_type, from_node_id, to_node_id)
            confidence = float(data.get("confidence", 1.0))
            occurred_at = data.get("occurred_at")
            if isinstance(occurred_at, str):
                occurred_at = datetime.fromisoformat(occurred_at)

            existing = edges.get(edge_id)
            if existing is None:
                edges[edge_id] = KnowledgeGraphEdge(
                    case_id=case_id,
                    edge_id=edge_id,
                    from_node_id=from_node_id,
                    to_node_id=to_node_id,
                    relationship_type=relationship_type,
                    source_record_ids=[record.record_id],
                    observed_at=record.observed_at,
                    occurred_at=occurred_at,
                    confidence=confidence,
                    provenance=list(record.provenance),
                    assertion_type=record.assertion_type,
                )
                continue

            # Several records asserting the same relationship share one edge and
            # pool their evidence, rather than creating duplicate edge ids.
            if record.record_id not in existing.source_record_ids:
                existing.source_record_ids.append(record.record_id)
            existing.provenance.extend(record.provenance)
            existing.confidence = max(existing.confidence, confidence)
            existing.observed_at = _earliest(existing.observed_at, record.observed_at)
            existing.occurred_at = _earliest(existing.occurred_at, occurred_at)
            existing.assertion_type = weakest_assertion(
                [existing.assertion_type, record.assertion_type]
            )

        return KnowledgeGraph(
            graph_id=graph_id,
            case_id=case_id,
            nodes=nodes,
            edges=list(edges.values()),
            unresolved_record_ids=resolution.unresolved_record_ids,
            rejected_edges=rejected,
        )

    @staticmethod
    def evidence_for(graph: KnowledgeGraph, element_id: str) -> tuple[list[str], list[ProvenanceRecord]]:
        """Collect every piece of provenance held by elements matching ``element_id``."""
        element_types: list[str] = []
        evidence: list[ProvenanceRecord] = []
        for node in graph.nodes:
            if node.node_id == element_id:
                element_types.append("node")
                evidence.extend(node.provenance)
        for edge in graph.edges:
            if edge.edge_id == element_id:
                element_types.append("edge")
                evidence.extend(edge.provenance)
        return element_types, evidence
