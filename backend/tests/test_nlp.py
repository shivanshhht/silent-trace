from datetime import datetime, timezone

import pytest

from app.schemas.nlp import ReportRequest
from app.services.nlp_extraction import NLPExtractionService


CASE = "case_test-001"

REPORT = ReportRequest(
    case_id=CASE,
    report_id="rpt_test-001",
    source_record_id="src_report-test-001",
    observed_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    text=(
        "On 2026-01-09 18:30, Avery Rowan contacted Blair Keene using phone +1 (555) 010-2040. "
        "Avery drove vehicle ST-2040 at Demo Market and met Blair Keene. "
        "Avery was associated with Northstar Demo Cooperative in Example City. "
        "The incident, fictional handoff, was recorded."
    ),
)


def _by_id(extraction):
    return {entity.entity_id: entity for entity in extraction.extracted_entities}


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
    assert result.content_hash and result.extraction_run_id


def test_relationships_use_the_canonical_vocabulary_and_carry_evidence() -> None:
    result = NLPExtractionService().extract(REPORT)

    relationship_types = {r.relationship_type for r in result.extracted_relationships}
    assert {"contacted", "uses", "met", "associated_with"} <= relationship_types
    assert all(r.source_record_id == REPORT.source_record_id for r in result.extracted_relationships)
    assert all(0 <= r.confidence <= 1 and r.evidence for r in result.extracted_relationships)
    # Every NLP relationship is an interpretation, never an observation.
    assert all(r.assertion_type == "inferred" for r in result.extracted_relationships)


def test_organization_does_not_absorb_a_trailing_location() -> None:
    result = NLPExtractionService().extract(REPORT)

    organizations = [e.text for e in result.extracted_entities if e.entity_type == "ORGANIZATION"]
    locations = [e.text for e in result.extracted_entities if e.entity_type == "LOCATION"]

    assert organizations == ["Northstar Demo Cooperative"]
    assert "Example City" in locations


def test_incident_does_not_absorb_trailing_narrative() -> None:
    result = NLPExtractionService().extract(REPORT)

    incidents = [e.text for e in result.extracted_entities if e.entity_type == "INCIDENT"]

    assert incidents == ["fictional handoff"]


def test_repeated_mentions_of_one_person_form_a_single_entity() -> None:
    result = NLPExtractionService().extract(REPORT)

    people = [e for e in result.extracted_entities if e.entity_type == "PERSON"]
    names = sorted(person.text for person in people)

    assert names == ["Avery Rowan", "Blair Keene"]
    avery = next(person for person in people if person.text == "Avery Rowan")
    # "Avery" later in the report is another mention of the same person.
    assert len(avery.mentions) > 1


def test_evidence_snippets_are_not_truncated_mid_word() -> None:
    """A quote must start and end on a word boundary, never mid-word."""
    text = REPORT.text
    result = NLPExtractionService().extract(REPORT)

    for entity in result.extracted_entities:
        evidence = entity.evidence
        assert evidence == evidence.strip()
        start = text.index(evidence)
        end = start + len(evidence)
        assert start == 0 or not text[start - 1].isalnum()
        assert end == len(text) or not text[end].isalnum()


def test_empty_or_malformed_reports_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        NLPExtractionService().extract(REPORT.model_copy(update={"text": "   "}))


def test_output_adapts_into_the_canonical_record_shape() -> None:
    service = NLPExtractionService()
    extraction = service.extract(REPORT)

    records, rejected = service.to_ingested_records(REPORT, extraction)

    assert records
    assert all(record.case_id == CASE for record in records)
    assert all(record.provenance[0].source_record_id == REPORT.source_record_id for record in records)
    assert any(record.record_type == "person" for record in records)
    assert any(record.record_type == "relationship" for record in records)
    # DATE_TIME has no domain record, and that is reported rather than hidden.
    assert any("DATE_TIME" in message for message in rejected)
