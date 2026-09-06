"""Deterministic extraction over the controlled synthetic report format.

This is a rule-based extractor, not a language model. Its job in Stage A is to
be *honest* rather than complete: it should find less rather than assert
something the text does not support.

Three properties matter more than recall:

**Attribution is sentence-scoped.** A relationship subject is the nearest person
mention preceding the trigger phrase *within the same sentence*. If no person
precedes the trigger in that sentence, the relationship is omitted. Selecting a
globally-first person is what previously let a report stating "Blair Keene drove
vehicle X" be recorded as "Avery Rowan used vehicle X".

**Mentions include deterministic coreference.** A standalone first or last name
is treated as another mention of an already-extracted person, but only when it
matches exactly one of them. An ambiguous short name is ignored rather than
guessed.

**No fact is invented to satisfy a schema.** Attributes the text does not state
are omitted, so the domain model records them as absent instead of as a
plausible-looking value.
"""

from dataclasses import dataclass
from datetime import datetime
import re

from app.schemas.investigation import (
    IngestedRecord,
    ProvenanceRecord,
)
from app.schemas.nlp import (
    EXTRACTED_TYPE_TO_RECORD_TYPE,
    ExtractedEntity,
    ExtractedRelationship,
    ReportExtraction,
    ReportRequest,
    SourceSpan,
)
from app.services.identity import (
    content_hash,
    mint_entity_id,
    mint_extraction_run_id,
    mint_relationship_id,
    normalize_text,
)
from app.services.ingestion import format_error, validate_and_normalize


# Extraction type -> the entity-type name used for id minting.
_MINT_TYPE = {
    "PERSON": "person",
    "PHONE": "phone",
    "VEHICLE": "vehicle",
    "LOCATION": "location",
    "ORGANIZATION": "organization",
    "INCIDENT": "incident",
    "DATE_TIME": "date_time",
}

# (trigger pattern, canonical relationship type, allowed object types, confidence)
_RELATION_RULES: tuple[tuple[str, str, tuple[str, ...], float], ...] = (
    (r"\bcontacted\b", "contacted", ("PERSON", "PHONE"), 0.88),
    (r"\b(?:drove|was driving|used vehicle)\b", "uses", ("VEHICLE",), 0.88),
    (r"\bowns\b", "owns", ("VEHICLE",), 0.86),
    (r"\bmet\b", "met", ("PERSON",), 0.86),
    (r"\bassociated with\b", "associated_with", ("ORGANIZATION",), 0.86),
    (r"\bmember of\b", "member_of", ("ORGANIZATION",), 0.86),
    (r"\btransacted with\b", "transacted_with", ("PERSON", "ORGANIZATION"), 0.86),
    (r"\binvolved in\b", "involved_in", ("INCIDENT",), 0.78),
    (r"\b(?:at|in)\b", "located_at", ("LOCATION",), 0.80),
)

# A negation between the subject and the trigger inverts the claim. Asserting
# the relationship anyway would state the opposite of the source, so the
# relationship is withheld and the omission is reported.
_NEGATION = re.compile(r"\b(?:not|never|no longer|denied|denies|deny|neither|nor)\b", re.IGNORECASE)


@dataclass
class _Candidate:
    """One surface occurrence of a possible entity, before grouping."""

    entity_type: str
    text: str
    normalized: str
    start: int
    end: int
    confidence: float

    @property
    def key(self) -> tuple[str, str]:
        return (self.entity_type, self.normalized)


class NLPExtractionService:
    """Extract explicit entities and relationships from synthetic reports."""

    _phone = re.compile(r"\+?\d[\d ()-]{6,}\d")
    _vehicle = re.compile(r"\b[A-Z]{1,3}[- ]\d{3,5}\b")
    _date_time = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?Z?\b")
    _person = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")
    _capitalized_phrase = r"[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*"
    _organization = re.compile(rf"\bassociated with\s+({_capitalized_phrase})")
    _location = re.compile(rf"\b(?:at|to|in)\s+({_capitalized_phrase})")
    # Stops at a comma so trailing narrative ("..., was recorded") is not
    # absorbed into the incident description.
    _incident = re.compile(r"\bincident,?\s+([A-Za-z][^.,]*)")

    def extract(self, report: ReportRequest) -> ReportExtraction:
        text = report.text
        if not text.strip():
            raise ValueError("report text must not be empty")

        text_hash = content_hash(text)
        run_id = mint_extraction_run_id(report.case_id, report.report_id, text_hash)

        candidates = self._collect_candidates(text)
        entities, mentions = self._group(report, candidates, text)
        relationships, notes = self._extract_relationships(report, text, entities, mentions)

        warnings: list[str] = list(notes)
        if not entities:
            warnings.append("no supported entities found")
        if entities and not relationships:
            warnings.append(
                "entities were found but no relationship phrase could be attributed to a subject"
            )

        return ReportExtraction(
            case_id=report.case_id,
            report_id=report.report_id,
            source_record_id=report.source_record_id,
            content_hash=text_hash,
            extraction_run_id=run_id,
            extracted_entities=entities,
            extracted_relationships=relationships,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Entity extraction
    # ------------------------------------------------------------------

    def _collect_candidates(self, text: str) -> list[_Candidate]:
        """Find surface occurrences, most specific patterns first.

        Person matching runs last and skips spans already claimed by another
        type, so a place or organisation name is never also reported as a
        person.
        """
        candidates: list[_Candidate] = []
        claimed: list[tuple[int, int]] = []

        def claim(candidate: _Candidate) -> None:
            candidates.append(candidate)
            claimed.append((candidate.start, candidate.end))

        def overlaps(start: int, end: int) -> bool:
            return any(start < other_end and end > other_start for other_start, other_end in claimed)

        for match in self._date_time.finditer(text):
            value = match.group(0)
            claim(_Candidate("DATE_TIME", value, value, match.start(), match.end(), 0.99))

        for match in self._phone.finditer(text):
            value = match.group(0)
            if overlaps(match.start(), match.end()):
                continue
            digits = "".join(character for character in value if character.isdigit() or character == "+")
            claim(_Candidate("PHONE", value, digits, match.start(), match.end(), 0.99))

        for match in self._vehicle.finditer(text):
            value = match.group(0)
            if overlaps(match.start(), match.end()):
                continue
            claim(_Candidate("VEHICLE", value, value.replace(" ", "").upper(), match.start(), match.end(), 0.98))

        for match in self._organization.finditer(text):
            value = match.group(1).strip()
            if value and not overlaps(match.start(1), match.start(1) + len(value)):
                claim(_Candidate("ORGANIZATION", value, normalize_text(value), match.start(1), match.start(1) + len(value), 0.89))

        for match in self._location.finditer(text):
            value = match.group(1).strip()
            if value and not overlaps(match.start(1), match.start(1) + len(value)):
                claim(_Candidate("LOCATION", value, normalize_text(value), match.start(1), match.start(1) + len(value), 0.84))

        for match in self._incident.finditer(text):
            value = match.group(1).strip()
            if value and not overlaps(match.start(1), match.start(1) + len(value)):
                claim(_Candidate("INCIDENT", value, normalize_text(value), match.start(1), match.start(1) + len(value), 0.80))

        for match in self._person.finditer(text):
            value = match.group(0)
            if overlaps(match.start(), match.end()):
                continue
            claim(_Candidate("PERSON", value, normalize_text(value), match.start(), match.end(), 0.90))

        candidates.extend(self._coreference_mentions(text, candidates, claimed))
        return sorted(candidates, key=lambda candidate: candidate.start)

    def _coreference_mentions(
        self, text: str, candidates: list[_Candidate], claimed: list[tuple[int, int]]
    ) -> list[_Candidate]:
        """Resolve standalone first/last names onto an already-extracted person.

        A name token that matches more than one extracted person is ambiguous
        and produces no mention at all.
        """
        people = [candidate for candidate in candidates if candidate.entity_type == "PERSON"]
        owners: dict[str, set[str]] = {}
        for person in people:
            for token in person.text.split():
                if len(token) >= 3:
                    owners.setdefault(token, set()).add(person.normalized)

        extra: list[_Candidate] = []
        for token, normalized_values in owners.items():
            if len(normalized_values) != 1:
                continue  # ambiguous short name; do not guess which person it is
            normalized = next(iter(normalized_values))
            owner = next(person for person in people if person.normalized == normalized)
            for match in re.finditer(rf"\b{re.escape(token)}\b", text):
                if any(match.start() < end and match.end() > start for start, end in claimed):
                    continue
                extra.append(
                    _Candidate(
                        "PERSON", owner.text, normalized, match.start(), match.end(), owner.confidence
                    )
                )
        return extra

    def _group(
        self, report: ReportRequest, candidates: list[_Candidate], text: str
    ) -> tuple[list[ExtractedEntity], list[tuple[_Candidate, str]]]:
        """Collapse occurrences into entities, keeping every mention span."""
        order: list[tuple[str, str]] = []
        grouped: dict[tuple[str, str], list[_Candidate]] = {}
        for candidate in candidates:
            if candidate.key not in grouped:
                grouped[candidate.key] = []
                order.append(candidate.key)
            grouped[candidate.key].append(candidate)

        entities: list[ExtractedEntity] = []
        entity_id_by_key: dict[tuple[str, str], str] = {}
        for key in order:
            occurrences = grouped[key]
            primary = occurrences[0]
            entity_id = mint_entity_id(report.case_id, _MINT_TYPE[primary.entity_type], primary.normalized)
            entity_id_by_key[key] = entity_id
            entities.append(
                ExtractedEntity(
                    entity_id=entity_id,
                    case_id=report.case_id,
                    entity_type=primary.entity_type,  # type: ignore[arg-type]
                    text=primary.text,
                    normalized_value=primary.normalized,
                    confidence=primary.confidence,
                    source_record_id=report.source_record_id,
                    span=SourceSpan(start=primary.start, end=primary.end, text=text[primary.start:primary.end]),
                    mentions=[
                        SourceSpan(start=item.start, end=item.end, text=text[item.start:item.end])
                        for item in occurrences
                    ],
                    evidence=self._evidence(text, primary.start, primary.end),
                    assertion_type="inferred",
                )
            )

        mentions = [(candidate, entity_id_by_key[candidate.key]) for candidate in candidates]
        return entities, mentions

    # ------------------------------------------------------------------
    # Relationship extraction
    # ------------------------------------------------------------------

    def _extract_relationships(
        self,
        report: ReportRequest,
        text: str,
        entities: list[ExtractedEntity],
        mentions: list[tuple[_Candidate, str]],
    ) -> tuple[list[ExtractedRelationship], list[str]]:
        by_id = {entity.entity_id: entity for entity in entities}
        found: dict[tuple[str, str, str], ExtractedRelationship] = {}
        notes: list[str] = []

        for sentence_start, sentence_end in self._sentences(text):
            local = [
                (candidate, entity_id)
                for candidate, entity_id in mentions
                if candidate.start >= sentence_start and candidate.end <= sentence_end
            ]
            if not local:
                continue
            occurred_at = self._sentence_datetime(local)

            for pattern, relationship_type, object_types, confidence in _RELATION_RULES:
                for trigger in re.finditer(pattern, text[sentence_start:sentence_end], re.IGNORECASE):
                    trigger_start = sentence_start + trigger.start()
                    trigger_end = sentence_start + trigger.end()

                    subject = self._nearest_person_before(local, trigger_start)
                    if subject is None:
                        # Nothing in this sentence can carry the relationship.
                        # Attributing it to a person from elsewhere in the
                        # document would fabricate the association.
                        continue
                    target = self._first_object_after(local, trigger_end, object_types)
                    if target is None:
                        continue
                    if _NEGATION.search(text[subject[0].end:trigger_start]):
                        notes.append(
                            f"'{relationship_type}' near offset {trigger_start} was negated in the "
                            "source and was not recorded as a relationship"
                        )
                        continue

                    subject_id, target_id = subject[1], target[1]
                    if subject_id == target_id:
                        continue
                    key = (relationship_type, subject_id, target_id)
                    if key in found:
                        continue

                    found[key] = ExtractedRelationship(
                        relationship_id=mint_relationship_id(
                            report.case_id,
                            relationship_type,
                            subject_id,
                            target_id,
                            report.source_record_id,
                        ),
                        case_id=report.case_id,
                        relationship_type=relationship_type,  # type: ignore[arg-type]
                        source_entity_id=subject_id,
                        target_entity_id=target_id,
                        confidence=min(confidence, by_id[subject_id].confidence, by_id[target_id].confidence),
                        source_record_id=report.source_record_id,
                        span=SourceSpan(
                            start=trigger_start, end=trigger_end, text=text[trigger_start:trigger_end]
                        ),
                        evidence=self._evidence(text, trigger_start, trigger_end),
                        occurred_at=occurred_at,
                        assertion_type="inferred",
                    )
        return list(found.values()), notes

    @staticmethod
    def _nearest_person_before(
        local: list[tuple[_Candidate, str]], position: int
    ) -> tuple[_Candidate, str] | None:
        best: tuple[_Candidate, str] | None = None
        for candidate, entity_id in local:
            if candidate.entity_type == "PERSON" and candidate.end <= position:
                if best is None or candidate.end > best[0].end:
                    best = (candidate, entity_id)
        return best

    @staticmethod
    def _first_object_after(
        local: list[tuple[_Candidate, str]], position: int, object_types: tuple[str, ...]
    ) -> tuple[_Candidate, str] | None:
        best: tuple[_Candidate, str] | None = None
        for candidate, entity_id in local:
            if candidate.entity_type in object_types and candidate.start >= position:
                if best is None or candidate.start < best[0].start:
                    best = (candidate, entity_id)
        return best

    def _sentence_datetime(self, local: list[tuple[_Candidate, str]]) -> datetime | None:
        for candidate, _ in local:
            if candidate.entity_type == "DATE_TIME":
                parsed = self._parse_datetime(candidate.text)
                if parsed is not None:
                    return parsed
        return None

    # ------------------------------------------------------------------
    # Adapter into the canonical domain representation
    # ------------------------------------------------------------------

    def to_ingested_records(
        self, report: ReportRequest, extraction: ReportExtraction
    ) -> tuple[list[IngestedRecord], list[str]]:
        """Convert extraction output into validated canonical records.

        Every payload passes through the same validation boundary as structured
        ingestion. Anything that fails is returned as a rejection message rather
        than being coerced into a shape the schema will accept.
        """
        records: list[IngestedRecord] = []
        rejected: list[str] = []

        for entity in extraction.extracted_entities:
            record_type = EXTRACTED_TYPE_TO_RECORD_TYPE.get(entity.entity_type)
            if record_type is None:
                rejected.append(
                    f"{entity.entity_id}: '{entity.entity_type}' has no canonical domain record type; "
                    "it is retained in the extraction output only"
                )
                continue
            payload = self._entity_payload(entity, extraction)
            record = self._build_record(
                report, extraction, entity.entity_id, record_type, payload, entity.mentions
            )
            if isinstance(record, str):
                rejected.append(record)
            else:
                records.append(record)

        for relationship in extraction.extracted_relationships:
            payload = {
                "record_id": relationship.relationship_id,
                "from_entity_id": relationship.source_entity_id,
                "to_entity_id": relationship.target_entity_id,
                "relationship_type": relationship.relationship_type,
                "source_record_id": report.source_record_id,
                "confidence": relationship.confidence,
            }
            if relationship.occurred_at is not None:
                payload["occurred_at"] = relationship.occurred_at.isoformat()
            record = self._build_record(
                report,
                extraction,
                relationship.relationship_id,
                "relationship",
                payload,
                [relationship.span],
            )
            if isinstance(record, str):
                rejected.append(record)
            else:
                records.append(record)

        return records, rejected

    def _build_record(
        self,
        report: ReportRequest,
        extraction: ReportExtraction,
        record_id: str,
        record_type: str,
        payload: dict,
        spans: list[SourceSpan],
    ) -> IngestedRecord | str:
        try:
            normalized = validate_and_normalize(record_type, payload)
        except Exception as exc:  # surfaced to the caller, never silently dropped
            return f"{record_id}: {format_error(exc)}"

        return IngestedRecord(
            case_id=report.case_id,
            record_id=record_id,
            record_type=record_type,  # type: ignore[arg-type]
            observed_at=report.observed_at,
            data=normalized,
            # The interpretation is the extractor's; the spans below are literal.
            assertion_type="inferred",
            provenance=[
                ProvenanceRecord(
                    case_id=report.case_id,
                    source_record_id=report.source_record_id,
                    record_id=record_id,
                    provenance_type="observed",
                    document_id=report.report_id,
                    content_hash=extraction.content_hash,
                    source_type="synthetic_report",
                    extraction_run_id=extraction.extraction_run_id,
                    character_start=span.start,
                    character_end=span.end,
                    snippet=span.text,
                    observed_at=report.observed_at,
                )
                for span in spans
            ],
        )

    @staticmethod
    def _entity_payload(entity: ExtractedEntity, extraction: ReportExtraction) -> dict:
        """Build a domain payload from what the text actually states.

        Attributes the report does not provide are omitted entirely, so the
        domain model stores them as absent rather than as an invented value.
        """
        if entity.entity_type == "PERSON":
            return {"entity_id": entity.entity_id, "display_name": entity.text}
        if entity.entity_type == "PHONE":
            return {"entity_id": entity.entity_id, "number": entity.normalized_value}
        if entity.entity_type == "VEHICLE":
            return {"entity_id": entity.entity_id, "registration": entity.normalized_value}
        if entity.entity_type == "LOCATION":
            return {"entity_id": entity.entity_id, "label": entity.text}
        if entity.entity_type == "ORGANIZATION":
            return {"entity_id": entity.entity_id, "name": entity.text}
        return {"entity_id": entity.entity_id, "summary": entity.text}

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sentences(text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        start = 0
        for match in re.finditer(r"[.!?]+(?:\s+|$)", text):
            spans.append((start, match.end()))
            start = match.end()
        if start < len(text):
            spans.append((start, len(text)))
        return spans

    @staticmethod
    def _evidence(text: str, start: int, end: int, window: int = 60) -> str:
        """Quote the surrounding text, snapped to word boundaries.

        A fixed-offset window truncates mid-word and produces quotes that look
        like corrupted evidence, so both edges are moved to whitespace.
        """
        left = max(0, start - window)
        right = min(len(text), end + window)
        if left > 0:
            boundary = text.find(" ", left)
            if boundary != -1 and boundary < start:
                left = boundary + 1
        if right < len(text):
            boundary = text.rfind(" ", end, right)
            if boundary != -1:
                right = boundary
        return text[left:right].strip()

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        cleaned = value.strip().replace("Z", "").replace(" ", "T")
        try:
            return datetime.fromisoformat(cleaned if "T" in cleaned else f"{cleaned}T00:00:00")
        except ValueError:
            return None
