/*
 * The evidence inspector - the return leg of the journey.
 *
 * From here an investigator goes back the other way: this is the document, this
 * is the exact text quoted from it, and these are the graph objects that text
 * supports. Where the extractor recorded a character span the span is rendered
 * inside the document text rather than merely described, because a quote you
 * can see in context is a different quality of evidence from one you cannot.
 */

import { useMemo } from 'react'
import Icon from '../common/Icon.jsx'
import { AssertionPill, EntityChip, PanelSection } from '../common/Bits.jsx'
import { EmptyState } from '../common/States.jsx'
import { EMPTY, formatDateTime, shortId } from '../../lib/format.js'
import { entitiesForEvidence, hasSpan, relationshipsForEvidence } from '../../lib/evidence.js'
import { relationshipLabel } from '../../lib/domain.js'

function DocumentText({ document, row }) {
  const content = document?.content
  if (!content) {
    return (
      <p className="doctext doctext--none">
        The stored document holds no text body, so there is nothing to quote from.
      </p>
    )
  }
  if (!hasSpan(row)) {
    return <p className="doctext">{content}</p>
  }
  const start = Math.max(0, Math.min(content.length, row.character_start))
  const end = Math.max(start, Math.min(content.length, row.character_end))
  return (
    <p className="doctext">
      {content.slice(0, start)}
      <mark className="doctext__span">{content.slice(start, end)}</mark>
      {content.slice(end)}
    </p>
  )
}

export function EvidenceInspector({ provenanceId, index, onSelectEntity, onSelectRelationship }) {
  const row = index.evidenceById.get(provenanceId)
  const document = row ? index.documentById.get(row.document_id) : null
  const run = row ? index.runById.get(row.extraction_run_id) : null

  const supportedEntities = useMemo(() => entitiesForEvidence(row, index), [row, index])
  const supportedRelationships = useMemo(
    () => relationshipsForEvidence(row, index),
    [row, index],
  )

  if (!row) return <EmptyState title="Evidence not found in this case" icon="alert" />

  return (
    <div className="inspector">
      <header className="inspector__head">
        <span className="eglyph" style={{ width: 32, height: 32, background: 'var(--surface-sunken)', color: 'var(--text-secondary)' }}>
          <Icon name="document" size={17} strokeWidth={1.5} />
        </span>
        <div className="inspector__ident">
          <h2 className="inspector__name">
            {document?.title ?? row.document_id ?? 'Analyst assertion'}
          </h2>
          <p className="inspector__sub">
            {row.source_type === 'analyst_assertion'
              ? 'Analyst assertion'
              : (document?.source_type ?? row.source_type ?? 'source record').replace(/_/g, ' ')}
            {document?.reliability ? ` · ${document.reliability} reliability` : null}
          </p>
        </div>
        <AssertionPill assertion={row.assertion_type} />
      </header>

      <div className="inspector__ids">
        <span className="mono">{row.provenance_id}</span>
        <span className="pill pill--square">{row.provenance_type} provenance</span>
      </div>

      <div className="inspector__body scroll">
        <PanelSection title={hasSpan(row) ? 'Quoted span in source' : 'Source text'}>
          <div className="docbox">
            <DocumentText document={document} row={row} />
            {hasSpan(row) ? (
              <p className="docbox__span mono">
                characters {row.character_start}–{row.character_end}
              </p>
            ) : null}
          </div>
        </PanelSection>

        <PanelSection title="Record">
          <dl className="kv">
            <dt>Record</dt>
            <dd className="mono">{row.record_id}</dd>
            <dt>Record type</dt>
            <dd>{(row.record_type ?? EMPTY).replace(/_/g, ' ')}</dd>
            <dt>Source record</dt>
            <dd className="mono">{row.source_record_id}</dd>
            <dt>Document</dt>
            <dd className="mono">{row.document_id ?? EMPTY}</dd>
            <dt>Collected</dt>
            <dd className="num">{formatDateTime(document?.collected_at ?? row.observed_at)}</dd>
            <dt>Extraction run</dt>
            <dd>
              {run ? (
                <>
                  <span className="mono">{run.run_id}</span>
                  <span className="kv__note">
                    {' '}
                    — {run.kind}, {run.status}, {run.accepted_count} accepted
                    {run.rejected_count ? `, ${run.rejected_count} rejected` : ''}
                  </span>
                </>
              ) : (
                <span className="kv__note">Not produced by an extraction run.</span>
              )}
            </dd>
            <dt>Content hash</dt>
            <dd className="mono" title={row.content_hash ?? undefined}>
              {row.content_hash ? shortId(row.content_hash, 20) : EMPTY}
            </dd>
          </dl>
        </PanelSection>

        <PanelSection title="Supports in the graph" count={supportedEntities.length + supportedRelationships.length}>
          {supportedEntities.length === 0 && supportedRelationships.length === 0 ? (
            <EmptyState
              icon="network"
              title="Nothing in the graph cites this row"
              detail="The record it supports did not resolve into an entity or relationship."
            />
          ) : (
            <div className="supports">
              {supportedEntities.length ? (
                <div>
                  <p className="eyebrow">Entities</p>
                  <div className="supports__row">
                    {supportedEntities.map((entity) => (
                      <EntityChip
                        key={entity.canonical_id}
                        entity={entity}
                        onSelect={onSelectEntity}
                        size="sm"
                      />
                    ))}
                  </div>
                </div>
              ) : null}
              {supportedRelationships.length ? (
                <div>
                  <p className="eyebrow">Relationships</p>
                  <div className="supports__col">
                    {supportedRelationships.map((relationship) => (
                      <button
                        key={relationship.relationship_id}
                        type="button"
                        className="reflink reflink--block"
                        onClick={() => onSelectRelationship(relationship.relationship_id)}
                      >
                        <span className="reflink__type">
                          {relationshipLabel(relationship.relationship_type)}
                        </span>
                        {index.labelOf(relationship.from_entity_id)}
                        <Icon name="arrowRight" size={11} />
                        {index.labelOf(relationship.to_entity_id)}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </PanelSection>
      </div>
    </div>
  )
}

export default EvidenceInspector
