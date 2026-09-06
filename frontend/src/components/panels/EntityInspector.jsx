/*
 * The entity inspector: an analytical surface, not a profile card.
 *
 * It answers three questions in order - what is this, where does it sit in the
 * network, and what supports it - and it shows only what the case actually
 * holds. No portrait, no invented biography, no field filled with a placeholder
 * because a layout wanted one.
 */

import { useMemo, useState } from 'react'
import Icon from '../common/Icon.jsx'
import {
  AssertionPill,
  ContextTag,
  EntityChip,
  EntityGlyph,
  PanelSection,
  Stat,
} from '../common/Bits.jsx'
import { EmptyState } from '../common/States.jsx'
import { EvidenceList } from './EvidenceList.jsx'
import { TraceAnalysis } from './TraceAnalysis.jsx'
import {
  entityLabel,
  entityMeta,
  entitySubtitle,
  priorityMeta,
  relationshipLabel,
} from '../../lib/domain.js'
import { formatDate, formatPercent, plural } from '../../lib/format.js'
import { evidenceForEntity } from '../../lib/evidence.js'
import { analyseEntity } from '../../lib/traceAnalysis.js'

const TABS = [
  { id: 'analysis', label: 'Analysis' },
  { id: 'connections', label: 'Connections' },
  { id: 'evidence', label: 'Evidence' },
]

export function EntityInspector({
  entityId,
  index,
  intel,
  onSelectEntity,
  onSelectRelationship,
  onOpenEvidence,
  onTraceFrom,
  onCreateConnection,
}) {
  const [tab, setTab] = useState('analysis')
  const entity = index.entityById.get(entityId)

  const analysis = useMemo(
    () => (entity ? analyseEntity(entityId, index, intel) : null),
    [entity, entityId, index, intel],
  )
  const evidence = useMemo(() => evidenceForEntity(entity, index), [entity, index])
  const relationships = index.edgesByEntity.get(entityId) ?? []
  const community = index.communityByEntity.get(entityId)
  const degree = index.degreeByEntity.get(entityId)
  const betweenness = index.betweennessByEntity.get(entityId)
  const temporal = index.temporalByEntity.get(entityId)

  if (!entity) {
    return <EmptyState title="Entity not found in this case" icon="alert" />
  }

  const meta = entityMeta(entity.entity_type)
  const subtitle = entitySubtitle(entity)
  const priority = analysis?.priority

  return (
    <div className="inspector">
      <header className="inspector__head">
        <EntityGlyph type={entity.entity_type} size={32} />
        <div className="inspector__ident">
          <h2 className="inspector__name">{entityLabel(entity)}</h2>
          <p className="inspector__sub">
            <span style={{ color: meta.color, fontWeight: 600 }}>{meta.label}</span>
            {subtitle ? <> · {subtitle}</> : null}
          </p>
        </div>
        {priority ? (
          <span className={`pill ${priorityMeta(priority).pill}`} title="Network priority from Stage C leads">
            {priorityMeta(priority).label} priority
          </span>
        ) : null}
      </header>

      <div className="inspector__ids">
        <span className="mono">{entity.canonical_id}</span>
        <span
          className={`pill pill--square ${entity.match_status === 'candidate_review' ? 'pill--medium' : 'pill--observed'}`}
          title={
            entity.match_status === 'candidate_review'
              ? 'Resolution was strong but not exact; this identity is awaiting adjudication.'
              : 'Resolved on an exact structured key.'
          }
        >
          {entity.match_status.replace(/_/g, ' ')} {formatPercent(entity.match_confidence)}
        </span>
        <AssertionPill assertion={entity.assertion_type} />
      </div>

      <div className="inspector__stats">
        <Stat label="Connections" value={relationships.length} />
        <Stat label="Evidence" value={entity.evidence_count} />
        <Stat
          label="Degree rank"
          value={degree ? `#${degree.rank}` : '—'}
          hint="Rank by number of direct relationships"
        />
        <Stat
          label="Betweenness"
          value={betweenness ? betweenness.value.toFixed(1) : '—'}
          hint="How often this entity lies on a shortest route"
        />
      </div>

      <div className="inspector__actions">
        <button type="button" className="btn btn--sm" onClick={() => onTraceFrom(entityId)}>
          <Icon name="trace" size={12} />
          Trace connections
        </button>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => onCreateConnection(entityId)}
        >
          <Icon name="plus" size={12} />
          Connect
        </button>
      </div>

      <nav className="tabs" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`tab${tab === item.id ? ' is-active' : ''}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
            {item.id === 'connections' ? (
              <span className="num tab__count">{relationships.length}</span>
            ) : null}
            {item.id === 'evidence' ? (
              <span className="num tab__count">{evidence.length}</span>
            ) : null}
          </button>
        ))}
      </nav>

      <div className="inspector__body scroll">
        {tab === 'analysis' ? (
          <>
            {community ? (
              <PanelSection title="Cluster">
                <div className="clusterbox">
                  <div className="clusterbox__head">
                    <Icon name="community" size={13} />
                    <strong>{community.community_id}</strong>
                    <span className="mono">{plural(community.size, 'member')}</span>
                    <span className="clusterbox__density num">
                      {formatPercent(community.internal_density)} internal
                    </span>
                  </div>
                  <div className="clusterbox__members">
                    {community.member_entity_ids
                      .filter((memberId) => memberId !== entityId)
                      .map((memberId) => (
                        <EntityChip
                          key={memberId}
                          size="sm"
                          entity={index.entityById.get(memberId)}
                          entityId={memberId}
                          label={index.labelOf(memberId)}
                          onSelect={onSelectEntity}
                        />
                      ))}
                  </div>
                </div>
              </PanelSection>
            ) : null}

            <TraceAnalysis
              analysis={analysis}
              index={index}
              onOpenEvidence={onOpenEvidence}
              onSelectRelationship={onSelectRelationship}
            />

            {analysis?.leads?.length ? (
              <PanelSection title="Investigative leads" count={analysis.leads.length}>
                <ul className="minilist">
                  {analysis.leads.map((lead) => (
                    <li key={lead.lead_id} className="minilead">
                      <span className={`pill ${priorityMeta(lead.network_priority).pill}`}>
                        {priorityMeta(lead.network_priority).label}
                      </span>
                      <span className="minilead__text">{lead.explanation}</span>
                    </li>
                  ))}
                </ul>
              </PanelSection>
            ) : null}
          </>
        ) : null}

        {tab === 'connections' ? (
          <PanelSection title="Relationships" count={relationships.length}>
            {relationships.length === 0 ? (
              <EmptyState
                icon="network"
                title="No relationships recorded"
                detail="This entity appears in the case but no source links it to another entity."
              />
            ) : (
              <ul className="minilist">
                {relationships.map((relationship) => {
                  const otherId =
                    relationship.from_entity_id === entityId
                      ? relationship.to_entity_id
                      : relationship.from_entity_id
                  const classified = index.contextByRelationship.get(relationship.relationship_id)
                  return (
                    <li key={relationship.relationship_id}>
                      <button
                        type="button"
                        className="relrow"
                        onClick={() => onSelectRelationship(relationship.relationship_id)}
                      >
                        <span className="relrow__top">
                          <span className="relrow__type">
                            {relationshipLabel(relationship.relationship_type)}
                          </span>
                          <AssertionPill
                            assertion={relationship.assertion_type}
                            analystCreated={relationship.analyst_created}
                          />
                        </span>
                        <span className="relrow__peer">
                          <Icon name="arrowRight" size={12} />
                          {index.labelOf(otherId)}
                        </span>
                        <span className="relrow__meta">
                          {classified ? <ContextTag context={classified.context} /> : null}
                          <span className="relrow__spacer" />
                          <span className="num">{formatPercent(relationship.confidence)}</span>
                          <span>{formatDate(relationship.occurred_at)}</span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </PanelSection>
        ) : null}

        {tab === 'evidence' ? (
          <PanelSection title="Supporting evidence" count={evidence.length}>
            <EvidenceList
              rows={evidence}
              index={index}
              onOpen={onOpenEvidence}
              emptyDetail="No provenance row references the records this entity was resolved from."
            />
            {temporal && !temporal.insufficient_data ? (
              <p className="inspector__note">
                Recorded activity spans {formatDate(temporal.first_event_at)} to{' '}
                {formatDate(temporal.last_event_at)}.
              </p>
            ) : null}
          </PanelSection>
        ) : null}
      </div>
    </div>
  )
}

export default EntityInspector
