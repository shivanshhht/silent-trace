"""Contracts for NLP extraction over synthetic unstructured reports.

Extraction emits the *canonical* relationship vocabulary directly. There is no
separate NLP relationship type system to translate afterwards, because a second
vocabulary is exactly how an unmapped semantic slips into the graph.

Everything produced here is an interpretation of text and is therefore an
``inferred`` assertion, even though the character span backing it is literally
present in the document and so carries ``observed`` provenance.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.investigation import (
    CASE_ID_PATTERN,
    SOURCE_RECORD_ID_PATTERN,
    AssertionType,
    IngestedRecord,
    RelationshipType,
    StrictModel,
)


ExtractedEntityType = Literal[
    "PERSON", "PHONE", "VEHICLE", "LOCATION", "ORGANIZATION", "DATE_TIME", "INCIDENT"
]

# Extraction type -> canonical domain record type. ``DATE_TIME`` has no domain
# record: it is used to time other assertions, and is reported rather than
# turned into an entity of its own.
EXTRACTED_TYPE_TO_RECORD_TYPE: dict[str, str] = {
    "PERSON": "person",
    "PHONE": "phone",
    "VEHICLE": "vehicle",
    "LOCATION": "location",
    "ORGANIZATION": "organization",
    "INCIDENT": "incident",
}


class SourceSpan(StrictModel):
    """An exact, quotable region of the source document."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)


class ExtractedEntity(StrictModel):
    entity_id: str
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    entity_type: ExtractedEntityType
    text: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    source_record_id: str = Field(pattern=SOURCE_RECORD_ID_PATTERN)
    span: SourceSpan
    mentions: list[SourceSpan] = Field(min_length=1)
    evidence: str = Field(min_length=1)
    assertion_type: AssertionType = "inferred"


class ExtractedRelationship(StrictModel):
    relationship_id: str
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    relationship_type: RelationshipType
    source_entity_id: str
    target_entity_id: str
    confidence: float = Field(ge=0, le=1)
    source_record_id: str = Field(pattern=SOURCE_RECORD_ID_PATTERN)
    span: SourceSpan
    evidence: str = Field(min_length=1)
    occurred_at: datetime | None = None
    assertion_type: AssertionType = "inferred"


class ReportExtraction(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    report_id: str = Field(pattern=r"^rpt_[a-z0-9-]+$")
    source_record_id: str = Field(pattern=SOURCE_RECORD_ID_PATTERN)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    extraction_run_id: str = Field(min_length=1)
    extracted_entities: list[ExtractedEntity] = Field(default_factory=list)
    extracted_relationships: list[ExtractedRelationship] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReportRequest(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    report_id: str = Field(pattern=r"^rpt_[a-z0-9-]+$")
    source_record_id: str = Field(pattern=SOURCE_RECORD_ID_PATTERN)
    text: str = Field(min_length=1, max_length=10000)
    observed_at: datetime
    graph_id: str | None = Field(default=None, pattern=r"^graph_[a-z0-9-]+$")


class BatchReportRequest(StrictModel):
    reports: list[ReportRequest] = Field(min_length=1)


class ReportPipelineResult(StrictModel):
    """Outcome of report -> extraction -> validation -> resolution -> graph.

    ``rejected_records`` lists extraction output that did not become a canonical
    record - either because it failed validation, or because it has no domain
    representation (a ``DATE_TIME`` times other assertions rather than being an
    entity). It is reported rather than silently discarded, so any gap between
    what was extracted and what entered the graph is always visible.
    """

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    graph_id: str = Field(pattern=r"^graph_[a-z0-9-]+$")
    extraction: ReportExtraction
    ingested_records: list[IngestedRecord] = Field(default_factory=list)
    rejected_records: list[str] = Field(default_factory=list)
    resolved_entity_count: int
    graph_node_count: int
    graph_edge_count: int
