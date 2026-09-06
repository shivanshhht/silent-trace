"""Shared service instances and the request-scoped database session.

The services are stateless: all investigation state now lives in the database,
so a single instance per process is correct and there is no in-memory store for
routers to disagree about. What every router must share instead is the *one*
pipeline, so that structured ingestion, NLP processing and direct graph
construction cannot diverge into separate write paths.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.services.pipeline import InvestigationPipeline, default_graph_id

pipeline = InvestigationPipeline()

# Retained for routers and tests that address a single stage directly.
resolver = pipeline.resolver
graph_service = pipeline.graph_service
extractor = pipeline.extractor
ingestion_service = pipeline.ingestion_service

SessionDep = Annotated[Session, Depends(get_session)]

__all__ = [
    "SessionDep",
    "default_graph_id",
    "extractor",
    "graph_service",
    "ingestion_service",
    "pipeline",
    "resolver",
]
