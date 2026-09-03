from difflib import SequenceMatcher
import re
import unicodedata

from app.schemas.graph import EntityResolutionResult, EvidenceReference, ResolvedEntity
from app.schemas.investigation import EntityType, IngestedRecord


ENTITY_TYPES: set[str] = {"person", "phone", "vehicle", "location", "organization"}
ENTITY_ID_PREFIX = {"person": "per_", "phone": "phn_", "vehicle": "veh_", "location": "loc_", "organization": "org_"}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", value.lower())


def resolution_key(entity_type: str, attributes: dict) -> str:
    if entity_type == "person":
        return normalize_text("|".join([attributes.get("display_name", ""), *attributes.get("aliases", [])]))
    if entity_type == "phone":
        return normalize_text(attributes.get("number", ""))
    if entity_type == "vehicle":
        return normalize_text(attributes.get("registration", ""))
    if entity_type == "location":
        return normalize_text(f"{attributes.get('label', '')}|{attributes.get('locality', '')}")
    if entity_type == "organization":
        return normalize_text(attributes.get("name", ""))
    return ""


def _entity_type(record: IngestedRecord) -> str | None:
    return record.record_type if record.record_type in ENTITY_TYPES else None


def _source_record_id(record: IngestedRecord) -> str:
    provenance = record.provenance[0]
    return provenance if isinstance(provenance, str) else str(provenance["source_record_id"])


class EntityResolutionService:
    """Resolve only strong structured matches; retain uncertain candidates for review."""

    def resolve(self, records: list[IngestedRecord]) -> EntityResolutionResult:
        entities: list[ResolvedEntity] = []
        by_type_key: dict[tuple[str, str], ResolvedEntity] = {}
        unresolved: list[str] = []

        for record in records:
            entity_type = _entity_type(record)
            if entity_type is None:
                continue
            key = resolution_key(entity_type, record.data)
            evidence = EvidenceReference(
                source_record_id=_source_record_id(record),
                record_id=record.record_id,
                observed_at=record.observed_at,
            )
            existing = by_type_key.get((entity_type, key)) if key else None
            if existing:
                existing.source_entity_ids.append(record.data["entity_id"])
                existing.provenance.append(evidence)
                existing.match_status = "exact_match"
                continue

            candidates = [
                entity for entity in entities
                if entity.entity_type == entity_type
                and key
                and resolution_key(entity_type, entity.attributes)
                and SequenceMatcher(None, key, resolution_key(entity_type, entity.attributes)).ratio() >= 0.88
            ]
            candidate_ids = [candidate.canonical_id for candidate in candidates]
            canonical_id = record.data["entity_id"]
            status = "canonical"
            confidence = 1.0
            if candidates:
                status = "candidate_review"
                confidence = max(SequenceMatcher(None, key, resolution_key(entity_type, candidate.attributes)).ratio() for candidate in candidates)
                unresolved.append(record.record_id)
            entity = ResolvedEntity(
                canonical_id=canonical_id,
                entity_type=entity_type,  # type: ignore[arg-type]
                attributes=record.data,
                source_entity_ids=[record.data["entity_id"]],
                provenance=[evidence],
                match_confidence=round(confidence, 4),
                match_status=status,  # type: ignore[arg-type]
                review_candidates=candidate_ids,
            )
            entities.append(entity)
            if key:
                by_type_key[(entity_type, key)] = entity

        return EntityResolutionResult(entities=entities, unresolved_record_ids=unresolved)
