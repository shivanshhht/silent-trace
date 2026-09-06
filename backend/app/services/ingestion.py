"""The canonical validation boundary.

Every record that reaches entity resolution or graph construction passes through
``validate_and_normalize`` first, whether it arrived as structured data or was
derived by NLP. There is deliberately only one such boundary: a second, more
permissive path would let unvalidated assertions into the graph.
"""

import json
import re

from pydantic import ValidationError

from app.schemas.investigation import (
    Communication,
    EvidenceSource,
    FinancialTransaction,
    Incident,
    IngestedRecord,
    IngestionResult,
    Location,
    Organization,
    Person,
    PhoneNumber,
    ProvenanceRecord,
    Relationship,
    SourceRecord,
    Vehicle,
)
from app.services.identity import content_hash


PAYLOAD_MODELS = {
    "person": Person,
    "phone": PhoneNumber,
    "vehicle": Vehicle,
    "location": Location,
    "organization": Organization,
    "incident": Incident,
    "communication": Communication,
    "financial_transaction": FinancialTransaction,
    "evidence_source": EvidenceSource,
    "relationship": Relationship,
}


def format_error(error: Exception) -> str:
    """Render a validation failure as a readable, field-level message."""
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        )
    return str(error)


def validate_and_normalize(record_type: str, payload: dict) -> dict:
    """Validate a payload against its typed domain model and return it normalized.

    Raises ``ValidationError`` or ``KeyError``. Callers are expected to surface
    the failure rather than substituting a value that would satisfy the schema.
    """
    model = PAYLOAD_MODELS[record_type]
    return model.model_validate(payload).model_dump(mode="json")


def payload_identifier(payload: dict) -> str | None:
    return payload.get("entity_id") or payload.get("record_id")


def payload_content_hash(payload: dict) -> str:
    """Deterministic SHA-256 over the normalized payload, for provenance pinning."""
    return content_hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))


class IngestionService:
    """Validate and normalize source records without coupling to a storage backend."""

    def ingest(self, case_id: str, dataset_id: str, records: list[SourceRecord]) -> IngestionResult:
        accepted: list[IngestedRecord] = []
        errors: list[str] = []
        seen_ids: set[str] = set()

        for index, source_record in enumerate(records):
            try:
                if source_record.case_id != case_id:
                    raise ValueError(
                        f"record case '{source_record.case_id}' does not match dataset case '{case_id}'"
                    )
                if not re.fullmatch(r"src_[a-z0-9-]+", source_record.source_record_id):
                    raise ValueError("source_record_id must use the stable src_ prefix")
                if source_record.record_id in seen_ids:
                    raise ValueError(f"duplicate record_id '{source_record.record_id}'")
                if source_record.record_id == source_record.source_record_id and source_record.record_type != "evidence_source":
                    raise ValueError("record_id must differ from its evidence source reference")

                payload = validate_and_normalize(source_record.record_type, source_record.payload)
                identifier = payload_identifier(payload)
                if identifier != source_record.record_id:
                    raise ValueError(
                        f"payload identifier '{identifier}' does not match record_id '{source_record.record_id}'"
                    )

                accepted.append(
                    IngestedRecord(
                        case_id=case_id,
                        record_id=source_record.record_id,
                        record_type=source_record.record_type,
                        observed_at=source_record.observed_at,
                        data=payload,
                        assertion_type="observed",
                        provenance=[
                            ProvenanceRecord(
                                case_id=case_id,
                                source_record_id=source_record.source_record_id,
                                record_id=source_record.record_id,
                                provenance_type="observed",
                                document_id=source_record.source_record_id,
                                content_hash=payload_content_hash(payload),
                                source_type="structured_record",
                                observed_at=source_record.observed_at,
                            )
                        ],
                    )
                )
                seen_ids.add(source_record.record_id)
            except (ValidationError, ValueError, KeyError) as exc:
                errors.append(f"record[{index}] {source_record.record_id}: {format_error(exc)}")

        return IngestionResult(
            case_id=case_id,
            dataset_id=dataset_id,
            accepted_records=accepted,
            errors=errors,
            accepted_count=len(accepted),
            rejected_count=len(records) - len(accepted),
        )
