"""In-process storage for built knowledge graphs.

Stage A keeps storage in memory deliberately; persistence is a later stage. What
matters here is that there is exactly *one* store, shared by every API path, so
a graph produced by the NLP pipeline is retrievable through the graph API.

The records that produced each graph are retained alongside it. That lets a
second report be folded into an existing case graph by rebuilding from the union
of records, which keeps resolution and integrity checks running over the whole
case rather than over one report in isolation.
"""

from app.schemas.graph import KnowledgeGraph
from app.schemas.investigation import IngestedRecord


class GraphStore:
    def __init__(self) -> None:
        self._graphs: dict[str, KnowledgeGraph] = {}
        self._records: dict[str, list[IngestedRecord]] = {}

    def put(self, graph: KnowledgeGraph, records: list[IngestedRecord]) -> None:
        self._graphs[graph.graph_id] = graph
        self._records[graph.graph_id] = list(records)

    def get(self, graph_id: str) -> KnowledgeGraph | None:
        return self._graphs.get(graph_id)

    def records_for(self, graph_id: str) -> list[IngestedRecord]:
        return list(self._records.get(graph_id, []))

    def merge_records(
        self, graph_id: str, new_records: list[IngestedRecord]
    ) -> list[IngestedRecord]:
        """Union stored records with new ones, keyed by record id.

        Extraction ids are deterministic, so re-processing an unchanged report
        replaces its records rather than duplicating them.
        """
        merged: dict[str, IngestedRecord] = {
            record.record_id: record for record in self.records_for(graph_id)
        }
        for record in new_records:
            merged[record.record_id] = record
        return list(merged.values())

    def clear(self) -> None:
        self._graphs.clear()
        self._records.clear()
