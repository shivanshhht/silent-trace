/*
 * Finding the evidence behind a graph object.
 *
 * Provenance is stored once and referenced from both entities and
 * relationships, so both lookups here go through the same index: the record ids
 * an object was built from, resolved to the provenance rows that support those
 * records. Nothing is reconstructed and nothing is guessed - if a record has no
 * provenance row, it contributes nothing rather than an empty placeholder.
 */

export function evidenceForRecordIds(recordIds, index) {
  const seen = new Set()
  const rows = []
  for (const recordId of recordIds ?? []) {
    for (const row of index.evidenceByRecordId.get(recordId) ?? []) {
      if (seen.has(row.provenance_id)) continue
      seen.add(row.provenance_id)
      rows.push(row)
    }
  }
  return rows
}

export const evidenceForEntity = (entity, index) =>
  entity ? evidenceForRecordIds(entity.source_entity_ids, index) : []

export const evidenceForRelationship = (relationship, index) =>
  relationship ? evidenceForRecordIds(relationship.source_record_ids, index) : []

export function evidenceByIds(provenanceIds, index) {
  const rows = []
  for (const id of provenanceIds ?? []) {
    const row = index.evidenceById.get(id)
    if (row) rows.push(row)
  }
  return rows
}

/** Which relationships an evidence row supports - the reverse trip, evidence to graph. */
export function relationshipsForEvidence(evidenceRow, index) {
  if (!evidenceRow) return []
  return index.relationships.filter((relationship) =>
    relationship.source_record_ids?.includes(evidenceRow.record_id),
  )
}

/** Which entities an evidence row supports. */
export function entitiesForEvidence(evidenceRow, index) {
  if (!evidenceRow) return []
  return index.entities.filter((entity) =>
    entity.source_entity_ids?.includes(evidenceRow.record_id),
  )
}

/** Character spans are the strongest provenance the system holds. */
export const hasSpan = (row) =>
  row?.character_start !== null &&
  row?.character_start !== undefined &&
  row?.character_end !== null &&
  row?.character_end !== undefined
