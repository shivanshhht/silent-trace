from datetime import datetime, timezone

from app.schemas.investigation import SourceRecord
from app.services.ingestion import IngestionService


CASE = "case_test-001"
SOURCE = "src_test-001"


def record(record_id: str = "phn_test-001", payload: dict | None = None, case_id: str = CASE) -> SourceRecord:
    return SourceRecord(
        case_id=case_id,
        record_id=record_id,
        record_type="phone",
        source_record_id=SOURCE,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        payload=payload or {"entity_id": record_id, "number": " +1 (555) 010-9999 "},
    )


def test_valid_ingestion_normalizes_and_preserves_provenance() -> None:
    result = IngestionService().ingest(CASE, "set_test-001", [record()])

    assert result.accepted_count == 1
    assert result.rejected_count == 0
    accepted = result.accepted_records[0]
    assert accepted.record_id == "phn_test-001"
    assert accepted.data["number"] == "+15550109999"
    assert accepted.case_id == CASE
    assert [reference.source_record_id for reference in accepted.provenance] == [SOURCE]


def test_structured_records_are_observed_assertions() -> None:
    accepted = IngestionService().ingest(CASE, "set_test-001", [record()]).accepted_records[0]

    assert accepted.assertion_type == "observed"
    assert accepted.provenance[0].provenance_type == "observed"
    assert accepted.provenance[0].content_hash is not None


def test_invalid_payload_is_reported_clearly() -> None:
    invalid = record(payload={"entity_id": "phn_test-001", "number": "12"})

    result = IngestionService().ingest(CASE, "set_test-001", [invalid])

    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert "number" in result.errors[0]
    assert "at least 7" in result.errors[0]


def test_required_fields_are_enforced() -> None:
    invalid = record(payload={"entity_id": "phn_test-001"})

    result = IngestionService().ingest(CASE, "set_test-001", [invalid])

    assert result.rejected_count == 1
    assert "number" in result.errors[0]


def test_stable_ids_and_duplicate_ids_are_rejected() -> None:
    result = IngestionService().ingest(CASE, "set_test-001", [record(), record()])

    assert result.accepted_count == 1
    assert result.rejected_count == 1
    assert "duplicate record_id" in result.errors[0]


def test_source_reference_is_required_for_ingestion() -> None:
    invalid = record(record_id="phn_test-002")
    invalid.source_record_id = "bad-source"

    result = IngestionService().ingest(CASE, "set_test-001", [invalid])

    assert result.rejected_count == 1
    assert "source_record_id" in result.errors[0] or "String should match pattern" in result.errors[0]


def test_record_from_another_case_is_rejected() -> None:
    foreign = record(record_id="phn_test-003", case_id="case_other-001")

    result = IngestionService().ingest(CASE, "set_test-001", [foreign])

    assert result.accepted_count == 0
    assert "does not match dataset case" in result.errors[0]
