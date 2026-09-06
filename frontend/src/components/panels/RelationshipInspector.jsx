/*
 * The relationship inspector.
 *
 * Two questions, answered in this order: what is this connection, and why does
 * Silent Trace believe it exists. The second is the reason the provenance block
 * is as prominent as the first - a link with no evidence behind it should look
 * as thin as it is.
 */

import { useMemo } from 'react'
import Icon from '../common/Icon.jsx'
import { AssertionPill, Caveat, ContextTag, EntityChip, PanelSection } from '../common/Bits.jsx'
import { EvidenceList } from './EvidenceList.jsx'
import { TraceAnalysis } from './TraceAnalysis.jsx'
import { EmptyState } from '../common/States.jsx'
import { assertionMeta, contextMeta, relationshipLabel } from '../../lib/domain.js'
import { EMPTY, formatDateTime, formatPercent } from '../../lib/format.js'
import { evidenceForRelationship } from '../../lib/evidence.js'
import { analyseRelationship } from '../../lib/traceAnalysis.js'

export function RelationshipInspector({
  relationshipId,
  index,
  onSelectEntity,
  onSelectRelationship,
  onOpenEvidence,
}) {
  const relationship = index.relationshipById.get(relationshipId)
  const classified = index.contextByRelationship.get(relationshipId)
  const evidence = useMemo(
    () => evidenceForRelationship(relationship, index),
    [relationship, index],
  )
  const analysis = useMemo(
    () => (relationship ? analyseRelationship(relationshipId, index) : null),
    [relationship, relationshipId, index],
  )

  if (!relationship) return <EmptyState title="Relationship not found in this case" icon="alert" />

  const from = index.entityById.get(relationship.from_entity_id)
  const to = index.entityById.get(relationship.to_entity_id)
  const claim = assertionMeta(relationship.assertion_type, relationship.analyst_created)
  const documents = [
    ...new Set(evidence.map((row) => row.document_id).filter(Boolean)),
  ]
  const runs = [...new Set(evidence.map((row) => row.extraction_run_id).filter(Boolean))]

  return (
    <div className="inspector">
      <header className="inspector__head inspector__head--rel">
        <div className="relhead">
          <EntityChip
            entity={from}
            entityId={relationship.from_entity_id}
            label={index.labelOf(relationship.from_entity_id)}
            onSelect={onSelectEntity}
          />
          <span className="relhead__verb">
            <span className="relhead__line" style={{ background: contextMeta(classified?.context).color }} />
            {relationshipLabel(relationship.relationship_type)}
            <Icon name="arrowRight" size={12} />
          </span>
          <EntityChip
            entity={to}
            entityId={relationship.to_entity_id}
            label={index.labelOf(relationship.to_entity_id)}
            onSelect={onSelectEntity}
          />
        </div>
      </header>

      <div className="inspector__ids">
        <span className="mono">{relationship.relationship_id}</span>
        <AssertionPill
          assertion={relationship.assertion_type}
          analystCreated={relationship.analyst_created}
        />
        {classified ? <ContextTag context={classified.context} /> : null}
      </div>

      {relationship.analyst_created ? (
        <div className="analystbanner">
          <Icon name="person" size={13} />
          <span>
            <strong>Analyst created.</strong> A human analyst asserted this link. No source
            document records it, so it is held as an inferred claim and its provenance points at
            the assertion itself.
          </span>
        </div>
      ) : null}

      <div className="inspector__body scroll">
        <PanelSection title="Claim">
          <dl className="kv">
            <dt>Type</dt>
            <dd>{relationshipLabel(relationship.relationship_type)}</dd>
            <dt>Context</dt>
            <dd>
              {classified ? (
                <>
                  {contextMeta(classified.context).label}
                  <span className="kv__note">
                    {classified.context_assertion === 'observed'
                      ? ' — stated by the source'
                      : ' — derived from the relationship type'}
                  </span>
                </>
              ) : (
                EMPTY
              )}
            </dd>
            <dt>How held</dt>
            <dd>
              {claim.label}
              <span className="kv__note"> — {claim.description}</span>
            </dd>
            <dt>Confidence</dt>
            <dd className="num">{formatPercent(relationship.confidence)}</dd>
            <dt>Occurred at</dt>
            <dd className="num">{formatDateTime(relationship.occurred_at)}</dd>
            <dt>Observed at</dt>
            <dd className="num">{formatDateTime(relationship.observed_at)}</dd>
            {classified?.analytical_note ? (
              <>
                <dt>Note</dt>
                <dd>{classified.analytical_note}</dd>
              </>
            ) : null}
          </dl>
        </PanelSection>

        <PanelSection title="Provenance">
          <dl className="kv">
            <dt>Source records</dt>
            <dd>
              <span className="idwrap">
                {relationship.source_record_ids.map((id) => (
                  <span className="idtag" key={id}>
                    <span className="mono idtag__value">{id}</span>
                  </span>
                ))}
              </span>
            </dd>
            <dt>Documents</dt>
            <dd>
              {documents.length ? (
                <span className="idwrap">
                  {documents.map((id) => (
                    <span className="idtag" key={id}>
                      <span className="mono idtag__value">
                        {index.documentById.get(id)?.title ?? id}
                      </span>
                    </span>
                  ))}
                </span>
              ) : (
                <span className="kv__note">No document — this claim is not document-backed.</span>
              )}
            </dd>
            <dt>Extraction runs</dt>
            <dd>
              {runs.length ? (
                <span className="idwrap">
                  {runs.map((id) => (
                    <span className="idtag" key={id}>
                      <span className="mono idtag__value">{id}</span>
                    </span>
                  ))}
                </span>
              ) : (
                <span className="kv__note">Not produced by an extraction run.</span>
              )}
            </dd>
          </dl>
        </PanelSection>

        <PanelSection title="Supporting evidence" count={evidence.length}>
          <EvidenceList
            rows={evidence}
            index={index}
            onOpen={onOpenEvidence}
            emptyDetail="No provenance row supports this relationship."
          />
        </PanelSection>

        <TraceAnalysis
          analysis={analysis}
          index={index}
          onOpenEvidence={onOpenEvidence}
          onSelectRelationship={onSelectRelationship}
        />

        <Caveat>
          A relationship records that a source asserted a link. It is not evidence of wrongdoing by
          either entity.
        </Caveat>
      </div>
    </div>
  )
}

export default RelationshipInspector
