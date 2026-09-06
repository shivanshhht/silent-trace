"""Deterministic entity resolution, scoped to a single investigation.

The logical identity of an entity is ``(case_id, entity_type, normalized_value)``.
Because ``case_id`` is part of the key, the same person, phone or vehicle
described in two investigations resolves to two distinct entities; nothing can
merge across a case boundary.

Only exact key matches merge. A strong-but-inexact similarity is never merged
silently: it produces a ``candidate_review`` entity carrying its confidence and
the ids it might correspond to, so a human decides. No criminality, guilt or
risk score is produced anywhere in this module.
"""

from difflib import SequenceMatcher

from app.schemas.graph import EntityResolutionResult, ResolvedEntity
from app.schemas.investigation import IngestedRecord, weakest_assertion
from app.services.identity import mint_entity_id, normalize_text


# Record types that carry an identity and can become graph nodes.
ENTITY_TYPES: set[str] = {"person", "phone", "vehicle", "location", "organization", "incident"}

# Similarity at or above this ratio is flagged for review, never auto-merged.
REVIEW_THRESHOLD = 0.88

__all__ = [
    "ENTITY_TYPES",
    "REVIEW_THRESHOLD",
    "EntityResolutionService",
    "normalize_text",
    "resolution_key",
]


def resolution_key(entity_type: str, attributes: dict) -> str:
    """Build the normalized identity value for an entity within its case.

    Optional attributes that the source did not state contribute an empty
    segment rather than a placeholder, so an unknown locality never makes two
    unrelated places look like the same place.
    """
    if entity_type == "person":
        aliases = attributes.get("aliases") or []
        return normalize_text("|".join([attributes.get("display_name") or "", *aliases]))
    if entity_type == "phone":
        return normalize_text(attributes.get("number") or "")
    if entity_type == "vehicle":
        return normalize_text(attributes.get("registration") or "")
    if entity_type == "location":
        return normalize_text(f"{attributes.get('label') or ''}|{attributes.get('locality') or ''}")
    if entity_type == "organization":
        return normalize_text(attributes.get("name") or "")
    if entity_type == "incident":
        return normalize_text(f"{attributes.get('incident_type') or ''}|{attributes.get('summary') or ''}")
    return ""


def _entity_type(record: IngestedRecord) -> str | None:
    return record.record_type if record.record_type in ENTITY_TYPES else None


class EntityResolutionService:
    """Resolve only strong structured matches; retain uncertain candidates for review."""

    def resolve(self, case_id: str, records: list[IngestedRecord]) -> EntityResolutionResult:
        foreign = [record.record_id for record in records if record.case_id != case_id]
        if foreign:
            raise ValueError(
                f"records {sorted(foreign)} do not belong to case '{case_id}'; "
                "entity resolution cannot span investigations"
            )

        entities: list[ResolvedEntity] = []
        by_key: dict[tuple[str, str], ResolvedEntity] = {}
        keys_by_canonical: dict[str, str] = {}
        unresolved: list[str] = []

        for record in records:
            entity_type = _entity_type(record)
            if entity_type is None:
                continue
            entity_id = record.data.get("entity_id")
            if not entity_id:
                unresolved.append(record.record_id)
                continue

            key = resolution_key(entity_type, record.data)
            if not key:
                # No identity can be computed, so this record cannot be merged
                # with anything. Surface it instead of guessing an identity.
                unresolved.append(record.record_id)
                continue

            existing = by_key.get((entity_type, key))
            if existing is not None:
                if entity_id not in existing.source_entity_ids:
                    existing.source_entity_ids.append(entity_id)
                existing.provenance.extend(record.provenance)
                existing.assertion_type = weakest_assertion(
                    [existing.assertion_type, record.assertion_type]
                )
                existing.match_status = "exact_match"
                continue

            candidate_ids: list[str] = []
            best_ratio = 0.0
            for candidate in entities:
                if candidate.entity_type != entity_type:
                    continue
                ratio = SequenceMatcher(None, key, keys_by_canonical[candidate.canonical_id]).ratio()
                if ratio >= REVIEW_THRESHOLD:
                    candidate_ids.append(candidate.canonical_id)
                    best_ratio = max(best_ratio, ratio)

            status = "canonical"
            confidence = 1.0
            if candidate_ids:
                status = "candidate_review"
                confidence = best_ratio
                unresolved.append(record.record_id)

            entity = ResolvedEntity(
                case_id=case_id,
                canonical_id=mint_entity_id(case_id, entity_type, key),
                entity_type=entity_type,  # type: ignore[arg-type]
                attributes=record.data,
                source_entity_ids=[entity_id],
                provenance=list(record.provenance),
                match_confidence=round(confidence, 4),
                match_status=status,  # type: ignore[arg-type]
                assertion_type=record.assertion_type,
                review_candidates=candidate_ids,
            )
            entities.append(entity)
            by_key[(entity_type, key)] = entity
            keys_by_canonical[entity.canonical_id] = key

        return EntityResolutionResult(
            case_id=case_id, entities=entities, unresolved_record_ids=unresolved
        )
