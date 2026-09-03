from datetime import datetime
import hashlib
import re

from app.schemas.investigation import IngestedRecord
from app.schemas.nlp import (
    ExtractedEntity,
    ExtractedRelationship,
    ReportExtraction,
    ReportRequest,
    SourceSpan,
)
from app.services.entity_resolution import normalize_text


class NLPExtractionService:
    """Extract explicit entities and relationships from the controlled synthetic report format."""

    _phone = re.compile(r"\+?\d[\d ()-]{6,}\d")
    _vehicle = re.compile(r"\b[A-Z]{1,3}[- ]\d{3,5}\b")
    _date_time = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?(?:Z)?\b")
    _person = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")

    def extract(self, report: ReportRequest) -> ReportExtraction:
        text = report.text.strip()
        if not text:
            raise ValueError("report text must not be empty")

        entities: list[ExtractedEntity] = []
        by_value: dict[tuple[str, str], ExtractedEntity] = {}

        def add(entity_type: str, value: str, start: int, confidence: float, normalized: str | None = None) -> ExtractedEntity:
            key = (entity_type, normalized or normalize_text(value))
            if key in by_value:
                return by_value[key]
            entity = ExtractedEntity(
                entity_id=self._stable_id(entity_type, normalized or value),
                entity_type=entity_type,  # type: ignore[arg-type]
                text=value,
                normalized_value=normalized or normalize_text(value),
                confidence=confidence,
                source_record_id=report.source_record_id,
                span=SourceSpan(start=start, end=start + len(value)),
                evidence=self._evidence(text, start),
            )
            entities.append(entity)
            by_value[key] = entity
            return entity

        for match in self._person.finditer(text):
            value = match.group(0)
            if value not in {"Example City", "Demo Market", "Northstar Demo", "Fictional Package"}:
                add("PERSON", value, match.start(), 0.94)
        for match in self._phone.finditer(text):
            value = match.group(0)
            if re.match(r"^\d{4}-\d{2}-\d{2}", value):
                continue
            add("PHONE", value, match.start(), 0.99, "".join(c for c in value if c.isdigit() or c == "+"))
        for match in self._vehicle.finditer(text):
            value = match.group(0)
            add("VEHICLE", value, match.start(), 0.98, value.replace(" ", "").upper())
        for match in self._date_time.finditer(text):
            add("DATE_TIME", match.group(0), match.start(), 0.99, match.group(0))

        for match in re.finditer(r"(?:at|to) ([A-Z][A-Za-z ]+?)(?= in | and |\.|,|$)", text):
            value = match.group(1).strip()
            if value and value not in {"19"}:
                add("LOCATION", value, match.start(1), 0.86)
        for match in re.finditer(r"associated with ([A-Z][A-Za-z ]+?)(?=\.|,| and )", text):
            value = match.group(1).strip()
            add("ORGANIZATION", value, match.start(1), 0.91)
        incident_match = re.search(r"incident,? ([a-zA-Z][^.]*)", text)
        if incident_match:
            value = incident_match.group(1).strip()
            add("INCIDENT", value, incident_match.start(1), 0.82)

        relationships = self._extract_relationships(report, text, entities)
        return ReportExtraction(
            report_id=report.report_id,
            source_record_id=report.source_record_id,
            extracted_entities=entities,
            extracted_relationships=relationships,
            warnings=[] if entities else ["no supported entities found"],
        )

    def to_ingested_records(self, report: ReportRequest, extraction: ReportExtraction) -> list[IngestedRecord]:
        records: list[IngestedRecord] = []
        for entity in extraction.extracted_entities:
            type_map = {"PERSON": "person", "PHONE": "phone", "VEHICLE": "vehicle", "LOCATION": "location", "ORGANIZATION": "organization", "INCIDENT": "incident"}
            record_type = type_map.get(entity.entity_type)
            if not record_type:
                continue
            data = self._entity_payload(entity, report.observed_at)
            records.append(IngestedRecord(record_id=entity.entity_id, record_type=record_type, observed_at=report.observed_at, data=data, provenance=[report.source_record_id]))  # type: ignore[arg-type]
        for relationship in extraction.extracted_relationships:
            records.append(IngestedRecord(record_id=relationship.relationship_id, record_type="relationship", observed_at=relationship.occurred_at or report.observed_at, data={"record_id": relationship.relationship_id, "from_entity_id": relationship.source_entity_id, "to_entity_id": relationship.target_entity_id, "relationship_type": relationship.relationship_type.lower(), "source_record_id": report.source_record_id, "confidence": relationship.confidence}, provenance=[report.source_record_id]))
        return records

    def _extract_relationships(self, report: ReportRequest, text: str, entities: list[ExtractedEntity]) -> list[ExtractedRelationship]:
        relationships: list[ExtractedRelationship] = []
        people = [entity for entity in entities if entity.entity_type == "PERSON"]
        phones = [entity for entity in entities if entity.entity_type == "PHONE"]
        vehicles = [entity for entity in entities if entity.entity_type == "VEHICLE"]
        locations = [entity for entity in entities if entity.entity_type == "LOCATION"]
        organizations = [entity for entity in entities if entity.entity_type == "ORGANIZATION"]
        incidents = [entity for entity in entities if entity.entity_type == "INCIDENT"]

        def add(kind: str, source: ExtractedEntity, target: ExtractedEntity, phrase: str, confidence: float = 0.9) -> None:
            position = text.lower().find(phrase.lower())
            evidence = text[max(0, position): min(len(text), position + len(phrase) + 100)] if position >= 0 else phrase
            relationships.append(ExtractedRelationship(relationship_id=self._stable_id("rel", f"{kind}|{source.entity_id}|{target.entity_id}"), relationship_type=kind, source_entity_id=source.entity_id, target_entity_id=target.entity_id, confidence=confidence, source_record_id=report.source_record_id, evidence=evidence, occurred_at=self._first_datetime(report.text)))

        if people and phones and re.search(r"contacted .* using phone", text, re.I): add("CONTACTED", people[0], phones[0], "contacted")
        if people and vehicles and re.search(r"drove vehicle", text, re.I): add("USED", people[0], vehicles[0], "drove vehicle")
        if people and locations and re.search(r"at .* and met", text, re.I): add("LOCATED_AT", people[0], locations[0], "at")
        if len(people) >= 2 and re.search(r"met ", text, re.I): add("MET", people[0], people[1], "met")
        if people and organizations and re.search(r"associated with", text, re.I): add("ASSOCIATED_WITH", people[0], organizations[0], "associated with")
        if people and incidents and re.search(r"incident", text, re.I): add("INVOLVED_IN", people[0], incidents[0], "incident", 0.84)
        if len(people) >= 2 and re.search(r"transacted with", text, re.I): add("TRANSACTED_WITH", people[0], people[1], "transacted with", 0.9)
        return relationships

    @staticmethod
    def _stable_id(prefix: str, value: str) -> str:
        return f"{prefix.lower()}_nlp-{hashlib.sha256(normalize_text(value).encode()).hexdigest()[:12]}"

    @staticmethod
    def _evidence(text: str, start: int) -> str:
        return text[max(0, start - 35): min(len(text), start + 100)].strip()

    @staticmethod
    def _first_datetime(text: str) -> datetime | None:
        match = re.search(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?Z?", text)
        if not match:
            return None
        value = match.group(0).replace("Z", "").replace(" ", "T")
        return datetime.fromisoformat(value if "T" in value else value + "T00:00:00")

    @staticmethod
    def _entity_payload(entity: ExtractedEntity, observed_at: datetime) -> dict:
        if entity.entity_type == "PERSON": return {"entity_id": entity.entity_id, "display_name": entity.text, "aliases": []}
        if entity.entity_type == "PHONE": return {"entity_id": entity.entity_id, "number": entity.normalized_value}
        if entity.entity_type == "VEHICLE": return {"entity_id": entity.entity_id, "registration": entity.normalized_value, "make_model": "Synthetic report vehicle"}
        if entity.entity_type == "LOCATION": return {"entity_id": entity.entity_id, "label": entity.text, "locality": "Synthetic locality"}
        if entity.entity_type == "ORGANIZATION": return {"entity_id": entity.entity_id, "name": entity.text, "organization_type": "synthetic organization"}
        return {"entity_id": entity.entity_id, "incident_type": entity.text, "occurred_at": observed_at.isoformat(), "location_id": "loc_nlp-unknown", "summary": entity.evidence}
