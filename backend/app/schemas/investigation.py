from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


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
    make_model: str = Field(min_length=1, max_length=80)
    color: str | None = None

    @field_validator("registration")
    @classmethod
    def normalize_registration(cls, value: str) -> str:
        return value.replace(" ", "").upper()


class Location(StrictModel):
    entity_id: str = Field(pattern=r"^loc_[a-z0-9-]+$")
    label: str = Field(min_length=1, max_length=160)
    locality: str = Field(min_length=1, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class Organization(StrictModel):
    entity_id: str = Field(pattern=r"^org_[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=160)
    organization_type: str = Field(min_length=1, max_length=80)


class Incident(StrictModel):
    entity_id: str = Field(pattern=r"^inc_[a-z0-9-]+$")
    incident_type: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    location_id: str = Field(pattern=r"^loc_[a-z0-9-]+$")
    summary: str = Field(min_length=1, max_length=500)


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
    record_id: str = Field(pattern=r"^src_[a-z0-9-]+$")
    source_type: Literal["synthetic_report", "synthetic_log", "synthetic_statement"]
    title: str = Field(min_length=1, max_length=160)
    collected_at: datetime
    reliability: Literal["low", "medium", "high"]
    content: str = Field(min_length=1, max_length=2000)


class Relationship(StrictModel):
    record_id: str = Field(pattern=r"^rel_[a-z0-9-]+$")
    from_entity_id: str = Field(min_length=5)
    to_entity_id: str = Field(min_length=5)
    relationship_type: Literal["located_at", "owns", "uses", "member_of", "associated_with"]
    source_record_id: str = Field(pattern=r"^(src|com|txn|inc)_[a-z0-9-]+$")
    confidence: float = Field(ge=0, le=1)


Payload = Annotated[
    Person | PhoneNumber | Vehicle | Location | Organization | Incident | Communication | FinancialTransaction | EvidenceSource | Relationship,
    Field(discriminator=None),
]


class SourceRecord(StrictModel):
    record_id: str = Field(pattern=r"^(src|com|txn|rel)_[a-z0-9-]+$|^(per|phn|veh|loc|org|inc)_[a-z0-9-]+$")
    record_type: RecordType
    source_record_id: str = Field(pattern=r"^src_[a-z0-9-]+$")
    observed_at: datetime
    payload: dict


class SyntheticDataset(StrictModel):
    dataset_id: str = Field(pattern=r"^set_[a-z0-9-]+$")
    description: str = Field(min_length=1)
    records: list[SourceRecord] = Field(min_length=1)


class IngestedRecord(StrictModel):
    record_id: str
    record_type: RecordType
    observed_at: datetime
    data: dict
    provenance: list[str | dict] = Field(min_length=1)


class IngestionResult(StrictModel):
    dataset_id: str
    accepted_records: list[IngestedRecord]
    errors: list[str] = Field(default_factory=list)
    accepted_count: int
    rejected_count: int


class IngestionRequest(StrictModel):
    dataset: SyntheticDataset
