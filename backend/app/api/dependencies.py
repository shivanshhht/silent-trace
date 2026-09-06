"""Shared service instances.

The ingestion, graph and NLP routers must operate on the same resolver and the
same graph store. Instantiating services per-router previously meant the NLP
pipeline built graphs into an object the graph API could not see.
"""

from app.services.entity_resolution import EntityResolutionService
from app.services.graph_store import GraphStore
from app.services.ingestion import IngestionService
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.nlp_extraction import NLPExtractionService


resolver = EntityResolutionService()
graph_service = KnowledgeGraphService(resolver)
graph_store = GraphStore()
ingestion_service = IngestionService()
extractor = NLPExtractionService()


def default_graph_id(case_id: str) -> str:
    """One graph per investigation by default, so reports accumulate per case."""
    return f"graph_{case_id.removeprefix('case_')}"
