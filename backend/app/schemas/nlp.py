from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.investigation import IngestedRecord, StrictModel


ExtractedEntityType = Literal["PERSON", "PHONE", "VEHICLE", "LOCATION", "ORGANIZATION", "DATE_TIME", "INCIDENT"]
ExtractedRelationshipType = Literal[
    "CONTACTED", "USED", "LOCATED_AT", "ASSOCIATED_WITH", "MET", "INVOLVED_IN", "TRANSACTED_WITH"
]


class SourceSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ExtractedEntity(StrictModel):
    entity_id: str
    entity_type: ExtractedEntityType
    text: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    source_record_id: str = Field(pattern=r"^src_[a-z0-9-]+$")
    span: SourceSpan
    evidence: str = Field(min_length=1)


class ExtractedRelationship(StrictModel):
    relationship_id: str
    relationship_type: ExtractedRelationshipType
    source_entity_id: str
    target_entity_id: str
    confidence: float = Field(ge=0, le=1)
    source_record_id: str = Field(pattern=r"^src_[a-z0-9-]+$")
    evidence: str = Field(min_length=1)
    occurred_at: datetime | None = None


class ReportExtraction(StrictModel):
    report_id: str = Field(pattern=r"^rpt_[a-z0-9-]+$")
    source_record_id: str = Field(pattern=r"^src_[a-z0-9-]+$")
    extracted_entities: list[ExtractedEntity]
    extracted_relationships: list[ExtractedRelationship]
    warnings: list[str] = Field(default_factory=list)


class ReportRequest(StrictModel):
    report_id: str = Field(pattern=r"^rpt_[a-z0-9-]+$")
    source_record_id: str = Field(pattern=r"^src_[a-z0-9-]+$")
    text: str = Field(min_length=1, max_length=10000)
    observed_at: datetime


class BatchReportRequest(StrictModel):
    reports: list[ReportRequest] = Field(min_length=1)


class ReportPipelineResult(StrictModel):
    extraction: ReportExtraction
    ingested_records: list[IngestedRecord]
    resolved_entity_count: int
    graph_node_count: int
    graph_edge_count: int
