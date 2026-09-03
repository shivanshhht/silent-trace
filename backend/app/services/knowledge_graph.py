from app.schemas.graph import KnowledgeGraph, KnowledgeGraphEdge, KnowledgeGraphNode, EvidenceReference
from app.schemas.investigation import IngestedRecord
from app.services.entity_resolution import EntityResolutionService
from app.services.entity_resolution import _source_record_id


class KnowledgeGraphService:
    def __init__(self, resolver: EntityResolutionService | None = None) -> None:
        self.resolver = resolver or EntityResolutionService()

    def build(self, graph_id: str, records: list[IngestedRecord]) -> KnowledgeGraph:
        resolution = self.resolver.resolve(records)
        nodes = {
            entity.canonical_id: KnowledgeGraphNode(
                node_id=entity.canonical_id,
                entity_type=entity.entity_type,
                attributes=entity.attributes,
                source_entity_ids=entity.source_entity_ids,
                provenance=entity.provenance,
            )
            for entity in resolution.entities
        }
        edges: list[KnowledgeGraphEdge] = []
        for record in records:
            if record.record_type not in {"communication", "financial_transaction", "relationship"}:
                continue
            data = record.data
            source = data.get("from_entity_id")
            target = data.get("to_entity_id")
            if not source or not target:
                continue
            edge_type = data.get("relationship_type") or record.record_type
            evidence = EvidenceReference(
                source_record_id=_source_record_id(record),
                record_id=record.record_id,
                observed_at=record.observed_at,
            )
            edges.append(
                KnowledgeGraphEdge(
                    edge_id=record.record_id,
                    from_node_id=self._canonical_id(source, nodes),
                    to_node_id=self._canonical_id(target, nodes),
                    relationship_type=edge_type,
                    source_record_id=_source_record_id(record),
                    observed_at=record.observed_at,
                    confidence=float(data.get("confidence", 1.0)),
                    provenance=[evidence],
                )
            )
        return KnowledgeGraph(graph_id=graph_id, nodes=list(nodes.values()), edges=edges)

    @staticmethod
    def _canonical_id(source_id: str, nodes: dict[str, KnowledgeGraphNode]) -> str:
        for node in nodes.values():
            if source_id in node.source_entity_ids:
                return node.node_id
        return source_id
