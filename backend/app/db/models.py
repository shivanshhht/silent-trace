"""Relational schema for a persisted investigation.

Design rules, in priority order:

1. **Case isolation is structural, not conventional.** Every table that holds
   case data carries ``case_id`` as part of its primary key and as a foreign key
   back to ``investigation_cases``. A row therefore cannot exist without a case,
   and an identifier such as ``src_demo-001`` may appear in two investigations
   as two genuinely distinct rows. Every repository lookup is keyed by case.

2. **Records are the authoritative state; entities, relationships and graphs are
   projections.** Stage A derives the whole graph deterministically from the
   validated record set. Persisting the projection as if it were independent
   truth would let the two drift, so the projection tables are rewritten from
   the records by the one pipeline rather than edited in place.

3. **Provenance is stored once and referenced.** An entity and an edge that rest
   on the same source span point at the same provenance row, so evidence cannot
   disagree with itself depending on which way it is queried.

The column types are chosen to run unchanged on PostgreSQL; ``JSON`` is declared
with a ``JSONB`` variant so the production database gets the indexable type.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


# PostgreSQL gets JSONB (indexable, binary); every other backend gets JSON.
JSONType = JSON().with_variant(JSONB, "postgresql")

ID = String(128)
CASE_ID = String(64)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _case_fk(*, ondelete: str = "CASCADE") -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["case_id"], ["investigation_cases.case_id"], ondelete=ondelete
    )


class InvestigationCase(Base):
    """The investigation itself. Every other row in the schema hangs off this."""

    __tablename__ = "investigation_cases"

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SourceDocument(Base):
    """A synthetic source document: a structured dataset entry or a report."""

    __tablename__ = "source_documents"
    __table_args__ = (_case_fk(),)

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    document_id: Mapped[str] = mapped_column(ID, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reliability: Mapped[str | None] = mapped_column(String(16), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionRun(Base):
    """One execution of the pipeline over one input, successful or not."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (_case_fk(),)

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    run_id: Mapped[str] = mapped_column(ID, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # structured | nlp | graph_build
    status: Mapped[str] = mapped_column(String(32))  # completed | partial | failed
    document_id: Mapped[str | None] = mapped_column(ID, nullable=True)
    dataset_id: Mapped[str | None] = mapped_column(ID, nullable=True)
    graph_id: Mapped[str | None] = mapped_column(ID, nullable=True)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSONType, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IngestedRecordRow(Base):
    """A record that passed the canonical validation boundary. Authoritative."""

    __tablename__ = "ingested_records"
    __table_args__ = (
        _case_fk(),
        ForeignKeyConstraint(
            ["case_id", "run_id"], ["ingestion_runs.case_id", "ingestion_runs.run_id"]
        ),
        Index("ix_records_case_type", "case_id", "record_type"),
    )

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    record_id: Mapped[str] = mapped_column(ID, primary_key=True)
    record_type: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assertion_type: Mapped[str] = mapped_column(String(16), default="observed")
    data: Mapped[dict] = mapped_column(JSONType)
    run_id: Mapped[str | None] = mapped_column(ID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProvenanceRow(Base):
    """The evidence atom: a link from an assertion back to a source span.

    ``provenance_id`` is a digest of the provenance content, so re-ingesting an
    unchanged document reuses the same row instead of accumulating duplicates.
    """

    __tablename__ = "provenance_records"
    __table_args__ = (
        _case_fk(),
        ForeignKeyConstraint(
            ["case_id", "record_id"],
            ["ingested_records.case_id", "ingested_records.record_id"],
            ondelete="CASCADE",
        ),
        Index("ix_provenance_case_record", "case_id", "record_id"),
    )

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    provenance_id: Mapped[str] = mapped_column(ID, primary_key=True)
    record_id: Mapped[str] = mapped_column(ID)
    source_record_id: Mapped[str] = mapped_column(ID)
    provenance_type: Mapped[str] = mapped_column(String(16), default="observed")
    document_id: Mapped[str | None] = mapped_column(ID, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_run_id: Mapped[str | None] = mapped_column(ID, nullable=True)
    character_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    character_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EntityRow(Base):
    """A resolved entity: a projection of the case records, not independent truth."""

    __tablename__ = "entities"
    __table_args__ = (_case_fk(),)

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    canonical_id: Mapped[str] = mapped_column(ID, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    canonical_value: Mapped[str] = mapped_column(String(500))
    attributes: Mapped[dict] = mapped_column(JSONType)
    source_entity_ids: Mapped[list] = mapped_column(JSONType, default=list)
    match_status: Mapped[str] = mapped_column(String(32))
    match_confidence: Mapped[float] = mapped_column(Float)
    assertion_type: Mapped[str] = mapped_column(String(16), default="observed")
    review_candidates: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RelationshipRow(Base):
    """A canonical relationship between two entities of the same case.

    Both endpoints are composite foreign keys into ``entities``, so the database
    enforces the same referential integrity the in-memory graph enforces: a
    relationship cannot reference an entity that is not in the case.
    """

    __tablename__ = "relationships"
    __table_args__ = (
        _case_fk(),
        ForeignKeyConstraint(
            ["case_id", "from_entity_id"], ["entities.case_id", "entities.canonical_id"]
        ),
        ForeignKeyConstraint(
            ["case_id", "to_entity_id"], ["entities.case_id", "entities.canonical_id"]
        ),
        Index("ix_relationships_case_type", "case_id", "relationship_type"),
    )

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    relationship_id: Mapped[str] = mapped_column(ID, primary_key=True)
    from_entity_id: Mapped[str] = mapped_column(ID)
    to_entity_id: Mapped[str] = mapped_column(ID)
    relationship_type: Mapped[str] = mapped_column(String(40))
    assertion_type: Mapped[str] = mapped_column(String(16), default="observed")
    confidence: Mapped[float] = mapped_column(Float)
    source_record_ids: Mapped[list] = mapped_column(JSONType, default=list)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EntityProvenance(Base):
    """Which evidence supports which entity."""

    __tablename__ = "entity_provenance"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "canonical_id"],
            ["entities.case_id", "entities.canonical_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["case_id", "provenance_id"],
            ["provenance_records.case_id", "provenance_records.provenance_id"],
            ondelete="CASCADE",
        ),
    )

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    canonical_id: Mapped[str] = mapped_column(ID, primary_key=True)
    provenance_id: Mapped[str] = mapped_column(ID, primary_key=True)


class RelationshipProvenance(Base):
    """Which evidence supports which relationship."""

    __tablename__ = "relationship_provenance"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "relationship_id"],
            ["relationships.case_id", "relationships.relationship_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["case_id", "provenance_id"],
            ["provenance_records.case_id", "provenance_records.provenance_id"],
            ondelete="CASCADE",
        ),
    )

    case_id: Mapped[str] = mapped_column(CASE_ID, primary_key=True)
    relationship_id: Mapped[str] = mapped_column(ID, primary_key=True)
    provenance_id: Mapped[str] = mapped_column(ID, primary_key=True)


class GraphSnapshot(Base):
    """A versioned, materialized knowledge graph for one case.

    The serialized nodes/edges let a graph be returned identically to the one
    Stage A built in memory, without re-running resolution on read. Each
    pipeline run appends a new version rather than overwriting, so the history
    of how the graph of a case evolved stays inspectable.
    """

    __tablename__ = "graph_snapshots"
    __table_args__ = (
        _case_fk(),
        UniqueConstraint("case_id", "graph_id", "version", name="uq_snapshot_version"),
        Index("ix_snapshot_graph_current", "graph_id", "is_current"),
    )

    snapshot_id: Mapped[str] = mapped_column(ID, primary_key=True)
    case_id: Mapped[str] = mapped_column(CASE_ID)
    graph_id: Mapped[str] = mapped_column(ID)
    version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    nodes: Mapped[list] = mapped_column(JSONType, default=list)
    edges: Mapped[list] = mapped_column(JSONType, default=list)
    unresolved_record_ids: Mapped[list] = mapped_column(JSONType, default=list)
    rejected_edges: Mapped[list] = mapped_column(JSONType, default=list)
    run_id: Mapped[str | None] = mapped_column(ID, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
