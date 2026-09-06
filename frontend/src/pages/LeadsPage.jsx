/*
 * Investigative leads.
 *
 * A lead here is required to explain itself. Each one keeps the individual
 * signals that produced it, with their own strength, confidence and wording, so
 * an investigator can see which parts of a lead are strong and which are thin -
 * and the fixed "indicator is not proof" caveat travels with every card.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../components/shell/AppShell.jsx'
import Icon from '../components/common/Icon.jsx'
import { Caveat, EntityChip, Meter, PanelSection } from '../components/common/Bits.jsx'
import { DataBoundary, EmptyState } from '../components/common/States.jsx'
import ContextDrawer from '../components/panels/ContextDrawer.jsx'
import { useInvestigation } from '../state/InvestigationContext.jsx'
import {
  CATEGORY_LABEL,
  LEAD_TYPE_LABEL,
  assertionMeta,
  priorityMeta,
} from '../lib/domain.js'
import { formatDateTime, formatPercent, plural } from '../lib/format.js'

const SIGNAL_KIND_COLOR = {
  anomaly: 'var(--priority-high)',
  indicator: 'var(--e-incident)',
  network: 'var(--e-person)',
}

function LeadCard({ lead, index, onSelectEntity, onOpenEvidence, onSelectRelationship }) {
  const [open, setOpen] = useState(false)
  const priority = priorityMeta(lead.network_priority)

  return (
    <article className={`leadfull leadfull--${lead.network_priority}`}>
      <header className="leadfull__head">
        <span className={`pill ${priority.pill}`}>{priority.label} priority</span>
        <h2 className="leadfull__type">{LEAD_TYPE_LABEL[lead.lead_type] ?? lead.lead_type}</h2>
        <span className="leadfull__conf">
          <Meter value={lead.confidence} color={priority.color} width={54} />
          <span className="num">{formatPercent(lead.confidence)}</span>
        </span>
      </header>

      <div className="leadfull__subjects">
        {lead.subject_entity_ids.map((entityId, position) => (
          <EntityChip
            key={entityId}
            entity={index.entityById.get(entityId)}
            entityId={entityId}
            label={lead.subject_labels[position] ?? index.labelOf(entityId)}
            onSelect={onSelectEntity}
          />
        ))}
      </div>

      <p className="leadfull__explanation">{lead.explanation}</p>

      <div className="leadfull__meta">
        <span>
          <strong className="num">{lead.signal_count}</strong> signals
        </span>
        <span>
          <strong className="num">{lead.independent_category_count}</strong> independent categories
        </span>
        <span>
          <strong className="num">{lead.evidence_ids.length}</strong> supporting evidence
        </span>
        <span className={`pill ${assertionMeta(lead.assertion_type).pill}`}>
          {assertionMeta(lead.assertion_type).label}
        </span>
        <span className="leadfull__spacer" />
        <span className="mono leadfull__stamp">{formatDateTime(lead.generated_at)}</span>
      </div>

      <button
        type="button"
        className="btn btn--sm leadfull__toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <Icon name={open ? 'chevronDown' : 'chevronRight'} size={11} />
        Why this lead exists
      </button>

      {open ? (
        <ol className="leadfull__signals">
          {lead.contributing_signals.map((signal, position) => (
            <li key={`${signal.signal_type}-${position}`}>
              <div className="lsignal">
                <span
                  className="lsignal__kind"
                  style={{ color: SIGNAL_KIND_COLOR[signal.source_kind] ?? 'var(--text-muted)' }}
                >
                  {signal.source_kind}
                </span>
                <div className="lsignal__body">
                  <p className="lsignal__title">
                    {signal.signal_type.replace(/_/g, ' ')}
                    <span className="lsignal__cat">
                      {CATEGORY_LABEL[signal.category] ?? signal.category}
                    </span>
                  </p>
                  <p className="lsignal__detail">{signal.explanation}</p>
                  <div className="lsignal__foot">
                    <span className="lsignal__strength">
                      <Meter
                        value={signal.signal_strength}
                        color={SIGNAL_KIND_COLOR[signal.source_kind] ?? 'var(--ink)'}
                        width={40}
                      />
                      <span className="num">{formatPercent(signal.signal_strength)} strength</span>
                    </span>
                    <span className="num">{formatPercent(signal.confidence)} confidence</span>
                    {signal.evidence_ids.length ? (
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => onOpenEvidence(signal.evidence_ids[0])}
                      >
                        Open evidence
                      </button>
                    ) : null}
                    {signal.relationship_ids.length ? (
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => onSelectRelationship(signal.relationship_ids[0])}
                      >
                        {plural(signal.relationship_ids.length, 'relationship')}
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ol>
      ) : null}

      <p className="leadfull__caveat">
        <Icon name="alert" size={12} />
        {lead.caveat}
      </p>
    </article>
  )
}

export function LeadsPage() {
  const { intel, index, selection, select, selectEntity, clearSelection, reload } = useInvestigation()
  const navigate = useNavigate()
  const [priorityFilter, setPriorityFilter] = useState(null)

  const leads = intel.data?.leads?.leads ?? []
  const visible = priorityFilter
    ? leads.filter((lead) => lead.network_priority === priorityFilter)
    : leads

  const counts = leads.reduce((totals, lead) => {
    totals[lead.network_priority] = (totals[lead.network_priority] ?? 0) + 1
    return totals
  }, {})

  return (
    <>
      <PageHeader
        title="Investigative leads"
        description="Where Stage C suggests looking next, and the signals behind each suggestion."
        actions={
          <div className="typefilter">
            <button
              type="button"
              className={`togglechip${priorityFilter === null ? ' is-on' : ''}`}
              onClick={() => setPriorityFilter(null)}
            >
              All <span className="num">{leads.length}</span>
            </button>
            {['high', 'medium', 'low'].map((level) =>
              counts[level] ? (
                <button
                  key={level}
                  type="button"
                  className={`togglechip${priorityFilter === level ? ' is-on' : ''}`}
                  onClick={() => setPriorityFilter(priorityFilter === level ? null : level)}
                >
                  <span
                    className="togglechip__swatch"
                    style={{ background: priorityMeta(level).color }}
                  />
                  {priorityMeta(level).label} <span className="num">{counts[level]}</span>
                </button>
              ) : null,
            )}
          </div>
        }
      />

      <div className="page splitpage">
        <div className="splitpage__main">
          <DataBoundary
            status={intel.status}
            error={intel.error}
            isEmpty={visible.length === 0}
            onRetry={reload}
            empty={
              <EmptyState
                icon="leads"
                title={leads.length ? 'No lead at this priority' : 'No leads raised for this investigation'}
                detail={
                  leads.length
                    ? 'Clear the filter to see every lead.'
                    : 'Stage C found no pattern here that clears its thresholds. A dense but ordinary network is expected to produce none — that is the control the engine is built to pass.'
                }
              />
            }
          >
            <>
              <div className="leadgrid">
                {visible.map((lead) => (
                  <LeadCard
                    key={lead.lead_id}
                    lead={lead}
                    index={index}
                    onSelectEntity={(id) => select('entity', id, 'leads')}
                    onOpenEvidence={(id) => select('evidence', id, 'leads')}
                    onSelectRelationship={(id) => select('relationship', id, 'leads')}
                  />
                ))}
              </div>
              <Caveat icon="alert">
                {intel.data?.leads?.caveat ??
                  'Indicator is not proof. A lead describes a structural or temporal pattern, not conduct.'}
              </Caveat>
            </>
          </DataBoundary>
        </div>

        {selection.kind ? (
          <div className="splitpage__side">
            <ContextDrawer
              inline
              selection={selection}
              index={index}
              intel={intel.data}
              onClose={clearSelection}
              onSelectEntity={(id) => select('entity', id, 'leads')}
              onSelectRelationship={(id) => select('relationship', id, 'leads')}
              onOpenEvidence={(id) => select('evidence', id, 'leads')}
              onTraceFrom={(id) => {
                selectEntity(id, 'leads')
                navigate('/network')
              }}
              onCreateConnection={() => navigate('/network')}
            />
          </div>
        ) : null}
      </div>
    </>
  )
}

export default LeadsPage
