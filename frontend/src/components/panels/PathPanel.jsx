/*
 * Path tracing.
 *
 * The panel that turns "are these two connected" into something an investigator
 * can read hop by hop. Every route comes from `analytics/paths`; the frontend
 * ranks nothing and computes nothing, it only chooses which returned route is
 * currently drawn on the canvas.
 */

import { useMemo } from 'react'
import Icon from '../common/Icon.jsx'
import { AssertionPill, Caveat, ContextTag, EntityChip, PanelSection } from '../common/Bits.jsx'
import { DataBoundary, EmptyState, Skeleton } from '../common/States.jsx'
import { TraceAnalysis } from './TraceAnalysis.jsx'
import { EvidenceList } from './EvidenceList.jsx'
import { entityIcon } from '../common/Icon.jsx'
import { relationshipLabel } from '../../lib/domain.js'
import { formatDate, formatPercent, plural } from '../../lib/format.js'
import { evidenceByIds } from '../../lib/evidence.js'
import { analysePath } from '../../lib/traceAnalysis.js'
import { ENTITY_HEX } from '../../lib/domain.js'

function Hop({ hop, position, index, onSelectRelationship, onOpenEvidence }) {
  const fromEntity = index.entityById.get(hop.from_entity_id)
  const toEntity = index.entityById.get(hop.to_entity_id)
  const evidence = evidenceByIds(hop.evidence_ids, index)

  return (
    <li className="hop">
      <span className="hop__index num">{position + 1}</span>
      <div className="hop__body">
        <div className="hop__ends">
          <span className="hop__end">
            <span style={{ color: ENTITY_HEX[fromEntity?.entity_type] ?? 'var(--text-muted)' }}>
              <Icon name={entityIcon(fromEntity?.entity_type)} size={12} strokeWidth={1.5} />
            </span>
            {hop.from_label}
          </span>
          <span className="hop__arrow">
            <Icon name="arrowRight" size={12} />
          </span>
          <span className="hop__end">
            <span style={{ color: ENTITY_HEX[toEntity?.entity_type] ?? 'var(--text-muted)' }}>
              <Icon name={entityIcon(toEntity?.entity_type)} size={12} strokeWidth={1.5} />
            </span>
            {hop.to_label}
          </span>
        </div>

        <button
          type="button"
          className="hop__rel"
          onClick={() => onSelectRelationship(hop.relationship_id)}
        >
          <span className="hop__reltype">{relationshipLabel(hop.relationship_type)}</span>
          <ContextTag context={hop.context} />
          <AssertionPill assertion={hop.assertion_type} />
          <span className="num hop__conf">{formatPercent(hop.confidence)}</span>
          <span className="hop__when num">{formatDate(hop.occurred_at ?? hop.observed_at)}</span>
        </button>

        {evidence.length ? (
          <div className="hop__evidence">
            <EvidenceList rows={evidence} index={index} onOpen={onOpenEvidence} />
          </div>
        ) : (
          <p className="hop__noevidence">
            {plural(hop.evidence_ids?.length ?? 0, 'evidence id')} cited, none loaded in this case
            view.
          </p>
        )}
      </div>
    </li>
  )
}

export function PathPanel({
  trace,
  pathResult,
  activePath,
  activePathIndex,
  setActivePathIndex,
  index,
  onSelectEntity,
  onSelectRelationship,
  onOpenEvidence,
  onChangeDepth,
  onClear,
}) {
  const paths = pathResult.data?.paths ?? []
  const analysis = useMemo(
    () => (activePath ? analysePath(activePath, index) : null),
    [activePath, index],
  )

  const source = trace.source
  const target = trace.target

  return (
    <div className="inspector">
      <header className="inspector__head">
        <span
          className="eglyph"
          style={{ width: 32, height: 32, background: 'var(--trace-soft)', color: 'var(--trace)' }}
        >
          <Icon name="trace" size={17} strokeWidth={1.5} />
        </span>
        <div className="inspector__ident">
          <h2 className="inspector__name">Trace path</h2>
          <p className="inspector__sub">Routes recorded between two entities</p>
        </div>
      </header>

      <div className="tracepick">
        <div className="tracepick__slot">
          <span className="eyebrow">From</span>
          {source ? (
            <EntityChip
              entity={index.entityById.get(source)}
              entityId={source}
              label={index.labelOf(source)}
              onSelect={onSelectEntity}
            />
          ) : (
            <span className="tracepick__empty">Click an entity on the graph</span>
          )}
        </div>
        <div className="tracepick__slot">
          <span className="eyebrow">To</span>
          {target ? (
            <EntityChip
              entity={index.entityById.get(target)}
              entityId={target}
              label={index.labelOf(target)}
              onSelect={onSelectEntity}
            />
          ) : (
            <span className="tracepick__empty">
              {source ? 'Click a second entity' : 'Waiting for the first entity'}
            </span>
          )}
        </div>
        <div className="tracepick__depth">
          <span className="eyebrow">Max hops</span>
          <div className="btn-group">
            {[1, 2, 3].map((depth) => (
              <button
                key={depth}
                type="button"
                className={`btn btn--sm${trace.maxDepth === depth ? ' is-active' : ''}`}
                onClick={() => onChangeDepth(depth)}
              >
                {depth}
              </button>
            ))}
          </div>
        </div>
        {source || target ? (
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClear}>
            Reset
          </button>
        ) : null}
      </div>

      <div className="inspector__body scroll">
        {!source || !target ? (
          <EmptyState
            icon="trace"
            title="Pick two entities"
            detail="Silent Trace will return every route between them up to the hop limit, each backed by the evidence for its hops."
          />
        ) : (
          <DataBoundary
            status={pathResult.status}
            error={pathResult.error}
            isEmpty={paths.length === 0}
            skeleton={<Skeleton rows={4} height={44} />}
            empty={
              <EmptyState
                icon="trace"
                title="No route within this hop limit"
                detail={
                  pathResult.data?.reason ??
                  'The recorded relationships do not connect these two entities that closely. Raising the hop limit may find one.'
                }
              />
            }
          >
            <>
              <PanelSection title="Routes found" count={pathResult.data?.count ?? paths.length}>
                <ul className="pathlist">
                  {paths.slice(0, 12).map((path, position) => (
                    <li key={`${path.source_entity_id}-${position}`}>
                      <button
                        type="button"
                        className={`pathopt${position === activePathIndex ? ' is-active' : ''}`}
                        onClick={() => setActivePathIndex(position)}
                      >
                        <span className="pathopt__len num">{path.length} hop</span>
                        <span className="pathopt__route truncate">
                          {path.edges[0].from_label}
                          {path.edges.map((hop) => ` → ${hop.to_label}`).join('')}
                        </span>
                        <span className="pathopt__conf num">
                          {formatPercent(path.path_confidence)}
                        </span>
                        <AssertionPill assertion={path.assertion_type} />
                      </button>
                    </li>
                  ))}
                </ul>
                {paths.length > 12 ? (
                  <p className="inspector__note">
                    Showing the first 12 of {paths.length} routes returned.
                  </p>
                ) : null}
              </PanelSection>

              {activePath ? (
                <PanelSection title="Selected route" count={activePath.length}>
                  <ul className="hoplist">
                    {activePath.edges.map((hop, position) => (
                      <Hop
                        key={hop.relationship_id}
                        hop={hop}
                        position={position}
                        index={index}
                        onSelectRelationship={onSelectRelationship}
                        onOpenEvidence={onOpenEvidence}
                      />
                    ))}
                  </ul>
                </PanelSection>
              ) : null}

              <TraceAnalysis
                analysis={analysis}
                index={index}
                onOpenEvidence={onOpenEvidence}
                onSelectRelationship={onSelectRelationship}
              />

              <Caveat icon="alert">
                A path is not proof. It shows that recorded relationships connect these entities,
                not that anything travelled along it.
              </Caveat>
            </>
          </DataBoundary>
        )}
      </div>
    </div>
  )
}

export default PathPanel
