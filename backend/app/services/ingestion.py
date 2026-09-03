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
    Relationship,
    SourceRecord,
    Vehicle,
)


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


class IngestionService:
    """Validate and normalize source records without coupling to a storage backend."""

    def ingest(self, dataset_id: str, records: list[SourceRecord]) -> IngestionResult:
        accepted: list[IngestedRecord] = []
        errors: list[str] = []
        seen_ids: set[str] = set()

        for index, source_record in enumerate(records):
            try:
                if not re.fullmatch(r"src_[a-z0-9-]+", source_record.source_record_id):
                    raise ValueError("source_record_id must use the stable src_ prefix")
                if source_record.record_id in seen_ids:
                    raise ValueError(f"duplicate record_id '{source_record.record_id}'")
                if source_record.record_id == source_record.source_record_id and source_record.record_type != "evidence_source":
                    raise ValueError("record_id must differ from its evidence source reference")

                model = PAYLOAD_MODELS[source_record.record_type]
                normalized = model.model_validate(source_record.payload)
                payload = normalized.model_dump(mode="json")
                payload_id = payload.get("entity_id") or payload.get("record_id")
                if payload_id != source_record.record_id:
                    raise ValueError(
                        f"payload identifier '{payload_id}' does not match record_id '{source_record.record_id}'"
                    )

                accepted.append(
                    IngestedRecord(
                        record_id=source_record.record_id,
                        record_type=source_record.record_type,
                        observed_at=source_record.observed_at,
                        data=payload,
                        provenance=[source_record.source_record_id],
                    )
                )
                seen_ids.add(source_record.record_id)
            except (ValidationError, ValueError, KeyError) as exc:
                errors.append(f"record[{index}] {source_record.record_id}: {self._format_error(exc)}")

        return IngestionResult(
            dataset_id=dataset_id,
            accepted_records=accepted,
            errors=errors,
            accepted_count=len(accepted),
            rejected_count=len(records) - len(accepted),
        )

    @staticmethod
    def _format_error(error: Exception) -> str:
        if isinstance(error, ValidationError):
            return "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in error.errors()
            )
        return str(error)
