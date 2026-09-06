"""Canonical identity minting and text normalization.

Every identifier Silent Trace generates itself is derived deterministically from
``(case_id, entity_type, normalized_value)``. This guarantees two properties the
pipeline depends on:

* **Stable within a case** - the same real-world entity described twice in one
  investigation collapses onto one identifier, regardless of record order.
* **Isolated across cases** - the same description appearing in two unrelated
  investigations yields two distinct identifiers, so evidence can never bleed
  between cases through a shared key.

Identifiers are opaque digests. Nothing downstream may parse them for meaning;
the typed prefix is retained only so the existing domain ID patterns
(``per_``, ``phn_``, ...) continue to validate.
"""

import hashlib
import re
import unicodedata


# Domain entity types that can become knowledge-graph nodes.
ENTITY_ID_PREFIX: dict[str, str] = {
    "person": "per_",
    "phone": "phn_",
    "vehicle": "veh_",
    "location": "loc_",
    "organization": "org_",
    "incident": "inc_",
    # ``date_time`` is an extraction artefact, not a domain entity. It is minted
    # so spans stay addressable, but the ingestion adapter deliberately emits no
    # domain record for it.
    "date_time": "dtm_",
}

_DIGEST_LENGTH = 16
_SEPARATOR = "\u0000"


def normalize_text(value: str) -> str:
    """Fold a value to its comparison form: ASCII, lowercase, alphanumeric only."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _digest(*parts: str) -> str:
    return hashlib.sha256(_SEPARATOR.join(parts).encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


def mint_entity_id(case_id: str, entity_type: str, normalized_value: str) -> str:
    """Mint the canonical identifier for an entity within one case."""
    prefix = ENTITY_ID_PREFIX.get(entity_type)
    if prefix is None:
        raise ValueError(f"no canonical id prefix registered for entity type '{entity_type}'")
    if not normalized_value:
        raise ValueError(f"cannot mint a {entity_type} id from an empty normalized value")
    return f"{prefix}{_digest(case_id, entity_type, normalized_value)}"


def mint_relationship_id(
    case_id: str,
    relationship_type: str,
    source_entity_id: str,
    target_entity_id: str,
    source_record_id: str,
) -> str:
    """Mint the id of a relationship *record*.

    The source document is part of the digest, so two documents asserting the
    same relationship produce two records. Those records later merge into a
    single graph edge carrying both pieces of provenance.
    """
    return f"rel_{_digest(case_id, relationship_type, source_entity_id, target_entity_id, source_record_id)}"


def mint_edge_id(case_id: str, relationship_type: str, from_node_id: str, to_node_id: str) -> str:
    """Mint the id of a graph *edge*.

    Deliberately excludes the source record: an edge is the assertion, and every
    record supporting it contributes provenance to the same edge.
    """
    return f"edg_{_digest(case_id, relationship_type, from_node_id, to_node_id)}"


def content_hash(text: str) -> str:
    """Full SHA-256 of source content, used to pin provenance to exact bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def mint_extraction_run_id(case_id: str, document_id: str, text_hash: str) -> str:
    """Mint a deterministic extraction-run id.

    Deterministic rather than random so that re-running extraction over
    unchanged input reproduces identical provenance, which keeps the pipeline
    testable and diffable.
    """
    return f"run_{_digest(case_id, document_id, text_hash)}"


def mint_provenance_id(
    case_id: str,
    record_id: str,
    source_record_id: str,
    character_start: int | None,
    character_end: int | None,
    snippet: str | None,
    extraction_run_id: str | None,
) -> str:
    """Mint a deterministic id for one piece of provenance.

    Derived from the evidence itself rather than from a counter, so persisting
    the same evidence twice updates one row instead of accumulating duplicates,
    and two identical spans in two cases stay distinct.
    """
    return f"prv_{_digest(case_id, record_id, source_record_id, str(character_start), str(character_end), snippet or '', extraction_run_id or '')}"
