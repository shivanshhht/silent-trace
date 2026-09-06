"""Canonical investigation domain models.

Two orthogonal semantics are modelled explicitly, and both must survive the
whole pipeline (source -> extraction -> resolution -> graph -> evidence API):

``AssertionType`` - the epistemic status of the *claim a record makes*.
    ``observed``  the fact is stated directly by the source data
    ``inferred``  the fact is the product of automated interpretation (e.g. NLP)
    ``unknown``   the system cannot establish the fact

``ProvenanceType`` - how the *supporting evidence* was located.
    ``observed``  an exact source span or source record backs the reference
    ``inferred``  the link back to the source was derived rather than stated
    ``unknown``   supporting evidence could not be established

These are independent. An NLP relationship is an ``inferred`` assertion backed
by ``observed`` provenance: the interpretation belongs to the machine, but the
quoted character span is literally present in the document.

A missing fact is represented as ``None``. No model in this module may be
populated with a placeholder value invented to satisfy a required field.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CASE_ID_PATTERN = r"^case_[a-z0-9-]+$"
SOURCE_RECORD_ID_PATTERN = r"^src_[a-z0-9-]+$"
RECORD_ID_PATTERN = r"^(per|phn|veh|loc|org|inc|src|com|txn|rel|dtm)_[a-z0-9-]+$"

AssertionType = Literal["observed", "inferred", "unknown"]
ProvenanceType = Literal["observed", "inferred", "unknown"]

# Ranked strongest-first: combining assertions keeps the weakest contributor so
# a record never gains certainty it did not already carry.
ASSERTION_STRENGTH: dict[str, int] = {"observed": 2, "inferred": 1, "unknown": 0}

EntityType = Literal[
    "person",
    "phone",
    "vehicle",
    "location",
    "organization",
    "incident",
]
RecordType = Literal[
    "person",
    "phone",
    "vehicle",
    "location",
    "organization",
    "incident",
    "communication",
    "financial_transaction",
    "evidence_source",
    "relationship",
]

# The single canonical relationship vocabulary. Structured records and NLP
# output both map into this set; nothing may enter the graph outside it.
RelationshipType = Literal[
    "located_at",
    "owns",
    "uses",
    "member_of",
    "associated_with",
    "contacted",
    "met",
    "involved_in",
    "transacted_with",
]

# Relational record types expressed as canonical relationships in the graph.
RECORD_TYPE_RELATIONSHIP: dict[str, str] = {
    "communication": "contacted",
    "financial_transaction": "transacted_with",
}

# The social/operational setting a relationship sits in. This is deliberately
# *stated by the source*, never guessed from personal attributes: inferring that
# two people are family because they share a surname would be exactly the kind
# of sensitive inference this system must not make. When a source does not state
# a context, analysis derives a structural one (communication, financial,
# geographic) from the relationship type instead, and otherwise reports
# ``unknown``.
RelationshipContext = Literal[
    "family",
    "community",
    "business",
    "communication",
    "financial",
    "geographic",
    "operational",
    "unknown",
]


def weakest_assertion(values: list[str]) -> str:
    """Combine assertion types conservatively: the weakest contributor wins."""
    if not values:
        return "unknown"
    return min(values, key=lambda value: ASSERTION_STRENGTH.get(value, 0))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProvenanceRecord(StrictModel):
    """A single, verifiable link from an assertion back to its source.

    ``case_id`` and ``source_record_id`` are mandatory: every assertion must be
    attributable to an investigation and to a source document. Span fields are
    optional because structured records have no character offsets, but when a
    span is supplied it must be complete and quotable - a start without an end,
    or without a snippet, is rejected rather than stored as misleading evidence.
    """

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    source_record_id: str = Field(pattern=SOURCE_RECORD_ID_PATTERN)
    record_id: str = Field(min_length=1)
    provenance_type: ProvenanceType = "observed"
    document_id: str | None = None
    content_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_type: str | None = None
    extraction_run_id: str | None = None
    character_start: int | None = Field(default=None, ge=0)
    character_end: int | None = Field(default=None, ge=0)
    snippet: str | None = None
    observed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_span(self) -> "ProvenanceRecord":
        has_start = self.character_start is not None
        has_end = self.character_end is not None
        if has_start != has_end:
            raise ValueError("character_start and character_end must be provided together")
        if has_start:
            if self.character_end <= self.character_start:
                raise ValueError("character_end must be greater than character_start")
            if not self.snippet:
                raise ValueError("a character span requires the quoted snippet it refers to")
        return self


class Person(StrictModel):
    entity_id: str = Field(pattern=r"^per_[a-z0-9-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    date_of_birth: str | None = None


class PhoneNumber(StrictModel):
    entity_id: str = Field(pattern=r"^phn_[a-z0-9-]+$")
    number: str = Field(min_length=7, max_length=32)
    label: str | None = None

    @field_validator("number")
    @classmethod
    def normalize_number(cls, value: str) -> str:
        normalized = "".join(character for character in value if character.isdigit() or character == "+")
        if len(normalized.replace("+", "")) < 7:
            raise ValueError("phone number must contain at least 7 digits")
        return normalized


class Vehicle(StrictModel):
    entity_id: str = Field(pattern=r"^veh_[a-z0-9-]+$")
    registration: str = Field(min_length=2, max_length=24)
    make_model: str | None = Field(default=None, max_length=80)
    color: str | None = None

    @field_validator("registration")
    @classmethod
    def normalize_registration(cls, value: str) -> str:
        return value.replace(" ", "").upper()


class Location(StrictModel):
    """A place.

    ``locality`` is optional. It stays ``None`` when the source does not state
    it, which stops two same-named places in different localities from silently
    collapsing onto one identity through an invented locality value.
    """

    entity_id: str = Field(pattern=r"^loc_[a-z0-9-]+$")
    label: str = Field(min_length=1, max_length=160)
    locality: str | None = Field(default=None, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class Organization(StrictModel):
    entity_id: str = Field(pattern=r"^org_[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=160)
    organization_type: str | None = Field(default=None, max_length=80)


class Incident(StrictModel):
    entity_id: str = Field(pattern=r"^inc_[a-z0-9-]+$")
    summary: str = Field(min_length=1, max_length=500)
    incident_type: str | None = Field(default=None, max_length=80)
    occurred_at: datetime | None = None
    location_id: str | None = Field(default=None, pattern=r"^loc_[a-z0-9-]+$")


class Communication(StrictModel):
    record_id: str = Field(pattern=r"^com_[a-z0-9-]+$")
    from_entity_id: str = Field(pattern=r"^(per|phn)_[a-z0-9-]+$")
    to_entity_id: str = Field(pattern=r"^(per|phn)_[a-z0-9-]+$")
    occurred_at: datetime
    channel: Literal["call", "message", "email"]
    duration_seconds: int | None = Field(default=None, ge=0)


class FinancialTransaction(StrictModel):
    record_id: str = Field(pattern=r"^txn_[a-z0-9-]+$")
    from_entity_id: str = Field(pattern=r"^(per|org)_[a-z0-9-]+$")
    to_entity_id: str = Field(pattern=r"^(per|org)_[a-z0-9-]+$")
    occurred_at: datetime
    amount: float = Field(gt=0)
    currency: Literal["SYN"]
    reference: str = Field(min_length=1, max_length=120)


class EvidenceSource(StrictModel):
    record_id: str = Field(pattern=SOURCE_RECORD_ID_PATTERN)
    source_type: Literal["synthetic_report", "synthetic_log", "synthetic_statement"]
    title: str = Field(min_length=1, max_length=160)
    collected_at: datetime
    reliability: Literal["low", "medium", "high"]
    content: str = Field(min_length=1, max_length=2000)


class Relationship(StrictModel):
    """A typed link between two entities, drawn from the canonical vocabulary.

    ``occurred_at`` is when the relationship itself happened, where the source
    states it. That is distinct from the envelope ``observed_at``, which is when
    the record was collected.
    """

    record_id: str = Field(pattern=r"^rel_[a-z0-9-]+$")
    from_entity_id: str = Field(min_length=5)
    to_entity_id: str = Field(min_length=5)
    relationship_type: RelationshipType
    source_record_id: str = Field(pattern=r"^(src|com|txn|inc)_[a-z0-9-]+$")
    confidence: float = Field(ge=0, le=1)
    occurred_at: datetime | None = None
    # Optional, and only ever populated when the source document states the
    # setting outright. Absent means unstated, not "none" - analysis must not
    # read a missing context as evidence of anything.
    context: RelationshipContext | None = None
    # True when a human analyst asserted this link rather than a document
    # stating it. Such a relationship is always an ``inferred`` assertion: no
    # source observed it, and the judgement belongs to the analyst. The flag is
    # kept distinct from ``assertion_type`` because "who claimed this" and "how
    # strongly it is held" are different questions.
    analyst_created: bool = False
    analyst_id: str | None = Field(default=None, max_length=120)
    analyst_note: str | None = Field(default=None, max_length=1000)


class SourceRecord(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    record_id: str = Field(pattern=RECORD_ID_PATTERN)
    record_type: RecordType
    source_record_id: str = Field(pattern=SOURCE_RECORD_ID_PATTERN)
    observed_at: datetime
    payload: dict


class SyntheticDataset(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    dataset_id: str = Field(pattern=r"^set_[a-z0-9-]+$")
    description: str = Field(min_length=1)
    records: list[SourceRecord] = Field(min_length=1)


class IngestedRecord(StrictModel):
    """A record that has passed the canonical validation boundary.

    Nothing may reach entity resolution or graph construction without this
    shape, whether it originated from structured ingestion or from NLP.
    """

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    record_id: str = Field(pattern=RECORD_ID_PATTERN)
    record_type: RecordType
    observed_at: datetime
    data: dict
    assertion_type: AssertionType = "observed"
    provenance: list[ProvenanceRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def provenance_stays_within_case(self) -> "IngestedRecord":
        for reference in self.provenance:
            if reference.case_id != self.case_id:
                raise ValueError(
                    f"provenance case '{reference.case_id}' does not match record case '{self.case_id}'"
                )
        return self


class IngestionResult(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    dataset_id: str
    accepted_records: list[IngestedRecord]
    errors: list[str] = Field(default_factory=list)
    accepted_count: int
    rejected_count: int


class IngestionRequest(StrictModel):
    dataset: SyntheticDataset
