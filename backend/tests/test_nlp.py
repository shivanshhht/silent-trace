from datetime import datetime, timezone

import pytest

from app.schemas.nlp import ReportRequest
from app.services.nlp_extraction import NLPExtractionService


REPORT = ReportRequest(
    report_id="rpt_test-001",
    source_record_id="src_report-test-001",
    observed_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    text="On 2026-01-09 18:30, Avery Rowan contacted Blair Keene using phone +1 (555) 010-2040. Avery drove vehicle ST-2040 at Demo Market and met Blair Keene. Avery was associated with Northstar Demo Cooperative in Example City. The incident, fictional handoff, was recorded.",
)


def test_extracts_multiple_entity_types_with_normalization_and_provenance() -> None:
    result = NLPExtractionService().extract(REPORT)
    types = {entity.entity_type for entity in result.extracted_entities}
    assert {"PERSON", "PHONE", "VEHICLE", "LOCATION", "ORGANIZATION", "DATE_TIME", "INCIDENT"} <= types
    phone = next(entity for entity in result.extracted_entities if entity.entity_type == "PHONE")
    assert phone.normalized_value == "+15550102040"
    assert phone.confidence >= 0.9
    assert phone.source_record_id == "src_report-test-001"
    assert phone.span.end > phone.span.start
    assert phone.evidence


def test_relationships_are_explicit_and_have_evidence() -> None:
    result = NLPExtractionService().extract(REPORT)
    relationship_types = {relationship.relationship_type for relationship in result.extracted_relationships}
    assert {"CONTACTED", "USED", "MET", "ASSOCIATED_WITH", "INVOLVED_IN"} <= relationship_types
    assert all(relationship.source_record_id == REPORT.source_record_id for relationship in result.extracted_relationships)
    assert all(0 <= relationship.confidence <= 1 and relationship.evidence for relationship in result.extracted_relationships)


def test_empty_or_malformed_reports_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        NLPExtractionService().extract(REPORT.model_copy(update={"text": "   "}))
    with pytest.raises(ValueError, match="must not be empty"):
        NLPExtractionService().extract(REPORT.model_copy(update={"text": ""}))


def test_output_adapts_into_existing_resolution_record_shape() -> None:
    service = NLPExtractionService()
    extraction = service.extract(REPORT)
    records = service.to_ingested_records(REPORT, extraction)
    assert records
    assert all(record.provenance == [REPORT.source_record_id] for record in records)
    assert any(record.record_type == "person" for record in records)
    assert any(record.record_type == "relationship" for record in records)
