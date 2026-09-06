/*
 * The Trace Analysis surface.
 *
 * It is deliberately not a chat panel. It answers one question about the object
 * currently selected - why is this analytically notable - by listing the Stage C
 * findings that mention it, each with the analysis that produced it and the
 * evidence behind it. When there is nothing to say it says nothing, which is the
 * whole point: an empty analysis is a real answer.
 */

import { useState } from 'react'
import Icon from '../common/Icon.jsx'
import { Caveat, Meter } from '../common/Bits.jsx'
import { formatPercent } from '../../lib/format.js'

const KIND_META = {
  network: { label: 'Network', icon: 'network', color: 'var(--e-person)' },
  structure: { label: 'Structure', icon: 'community', color: 'var(--e-vehicle)' },
  temporal: { label: 'Temporal', icon: 'clock', color: 'var(--e-location)' },
  anomaly: { label: 'Signal', icon: 'spark', color: 'var(--priority-high)' },
  indicator: { label: 'Indicator', icon: 'target', color: 'var(--e-incident)' },
  analyst: { label: 'Analyst', icon: 'person', color: 'var(--analyst)' },
}

function FactorRow({ factor, index, onOpenEvidence, onSelectRelationship }) {
  const [open, setOpen] = useState(false)
  const meta = KIND_META[factor.kind] ?? KIND_META.structure
  const references = (factor.evidenceIds?.length ?? 0) + (factor.relationshipIds?.length ?? 0)

  return (
    <li className="factor">
      <div className="factor__head">
        <span className="factor__kind" style={{ color: meta.color }}>
          <Icon name={meta.icon} size={12} strokeWidth={1.5} />
        </span>
        <div className="factor__body">
          <p className="factor__title">{factor.title}</p>
          <p className="factor__detail">{factor.detail}</p>
          <div className="factor__foot">
            <span className="mono factor__source" title="The analysis this came from">
              {factor.source}
            </span>
            {factor.metric ? <span className="factor__metric">{factor.metric}</span> : null}
            {typeof factor.strength === 'number' ? (
              <span className="factor__strength">
                <Meter value={factor.strength} color={meta.color} width={36} />
                <span className="num">{formatPercent(factor.strength)}</span>
              </span>
            ) : null}
            {references > 0 ? (
              <button
                type="button"
                className="btn btn--ghost btn--sm factor__more"
                onClick={() => setOpen((value) => !value)}
              >
                <Icon name={open ? 'chevronDown' : 'chevronRight'} size={11} />
                {factor.evidenceIds?.length ?? 0} evidence · {factor.relationshipIds?.length ?? 0} links
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {open ? (
        <div className="factor__refs">
          {factor.evidenceIds?.length ? (
            <div className="factor__refgroup">
              <p className="eyebrow">Evidence</p>
              <div className="factor__reflist">
                {factor.evidenceIds.map((id) => (
                  <button
                    key={id}
                    type="button"
                    className="reflink mono"
                    onClick={() => onOpenEvidence?.(id)}
                  >
                    {id}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {factor.relationshipIds?.length ? (
            <div className="factor__refgroup">
              <p className="eyebrow">Relationships</p>
              <div className="factor__reflist">
                {factor.relationshipIds.map((id) => {
                  const relationship = index.relationshipById.get(id)
                  return (
                    <button
                      key={id}
                      type="button"
                      className="reflink"
                      onClick={() => onSelectRelationship?.(id)}
                      disabled={!relationship}
                    >
                      {relationship
                        ? `${index.labelOf(relationship.from_entity_id)} → ${index.labelOf(
                            relationship.to_entity_id,
                          )}`
                        : id}
                    </button>
                  )
                })}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}

export function TraceAnalysis({ analysis, index, onOpenEvidence, onSelectRelationship }) {
  if (!analysis) return null

  return (
    <section className="tanalysis">
      <header className="tanalysis__head">
        <span className="tanalysis__mark" aria-hidden="true">
          <Icon name="trace" size={13} strokeWidth={1.5} />
        </span>
        <div>
          <h3 className="tanalysis__title">Trace Analysis</h3>
          <p className="tanalysis__sub">Composed from this case’s Stage C outputs</p>
        </div>
      </header>

      <p className="tanalysis__headline">{analysis.headline}</p>

      {analysis.empty ? (
        <p className="tanalysis__none">
          No centrality rank, community role, anomaly signal or indicator in this investigation
          names it. That is a finding in itself, not a gap.
        </p>
      ) : (
        <ul className="factorlist">
          {analysis.factors.map((factor, position) => (
            <FactorRow
              key={`${factor.source}-${factor.title}-${position}`}
              factor={factor}
              index={index}
              onOpenEvidence={onOpenEvidence}
              onSelectRelationship={onSelectRelationship}
            />
          ))}
        </ul>
      )}

      <Caveat>{analysis.caveat}</Caveat>
    </section>
  )
}

export default TraceAnalysis
