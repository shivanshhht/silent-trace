"""API contracts for persisted investigations.

Every ``confidence`` in this module is either an *entity-matching* confidence or
an *extraction* confidence, both inherited unchanged from Stage A. Nothing here
scores a person, and no field expresses guilt, risk or criminal probability. A
relationship is a link asserted by a document, not evidence of wrongdoing, and
the ``assertion_type`` on every row is what says whether the source observed it
or the machine inferred it.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.investigation import (
    CASE_ID_PATTERN,
    AssertionType,
    EntityType,
    ProvenanceType,
    RelationshipContext,
    RelationshipType,
    StrictModel,
)


CaseStatus = Literal["open", "active", "closed", "archived"]


class CreateInvestigationRequest(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: CaseStatus = "open"


class InvestigationSummary(StrictModel):
    """A case plus the size of what has been persisted for it."""

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    title: str
    description: str | None = None
    status: CaseStatus
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    run_count: int = 0
    record_count: int = 0
    entity_count: int = 0
    relationship_count: int = 0
    graph_id: str | None = None


class InvestigationListResponse(StrictModel):
    investigations: list[InvestigationSummary] = Field(default_factory=list)
    count: int = 0


class PersistedEntity(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    canonical_id: str
    entity_type: EntityType
    canonical_value: str
    attributes: dict
    source_entity_ids: list[str] = Field(default_factory=list)
    match_status: str
    match_confidence: float = Field(ge=0, le=1)
    assertion_type: AssertionType
    review_candidates: list[str] = Field(default_factory=list)
    evidence_count: int = 0


class EntityListResponse(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    entities: list[PersistedEntity] = Field(default_factory=list)
    count: int = 0


class CreateRelationshipRequest(StrictModel):
    """An analyst asserting a link between two entities already in the case.

    Both endpoints are canonical entity ids, the same ids the entities endpoint
    returns. The relationship type must come from the existing canonical
    vocabulary - an analyst may assert a link, but not invent a new kind of link,
    because a vocabulary the graph does not understand would be unanalysable.

    No document reference is accepted here by design. There is no document, and
    offering a field for one would invite a fabricated citation.
    """

    from_entity_id: str = Field(min_length=1, max_length=128)
    to_entity_id: str = Field(min_length=1, max_length=128)
    relationship_type: RelationshipType
    confidence: float = Field(default=1.0, ge=0, le=1)
    context: RelationshipContext | None = None
    analyst_id: str | None = Field(default=None, max_length=120)
    note: str | None = Field(
        default=None,
        max_length=1000,
        description="the reason the analyst is asserting this link",
    )
    occurred_at: datetime | None = None


class PersistedRelationship(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    relationship_id: str
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    assertion_type: AssertionType
    confidence: float = Field(ge=0, le=1)
    source_record_ids: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None
    occurred_at: datetime | None = None
    evidence_count: int = 0
    analyst_created: bool = Field(
        default=False,
        description=(
            "true when at least one piece of evidence on this relationship is an "
            "analyst assertion rather than a source document"
        ),
    )


class RelationshipListResponse(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    relationships: list[PersistedRelationship] = Field(default_factory=list)
    count: int = 0


class PersistedEvidence(StrictModel):
    """One provenance atom as stored, plus the record it supports.

    ``assertion_type`` is carried from the owning record rather than stored on
    the evidence itself: how a claim is held is a property of the claim, while
    ``provenance_type`` describes how its supporting span was located.
    """

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    provenance_id: str
    record_id: str
    record_type: str | None = None
    source_record_id: str
    document_id: str | None = None
    provenance_type: ProvenanceType
    assertion_type: AssertionType | None = None
    content_hash: str | None = None
    source_type: str | None = None
    extraction_run_id: str | None = None
    character_start: int | None = None
    character_end: int | None = None
    snippet: str | None = None
    observed_at: datetime | None = None


class EvidenceListResponse(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    evidence: list[PersistedEvidence] = Field(default_factory=list)
    count: int = 0
