/*
 * Overview answers one question: what is this investigation?
 *
 * Not a KPI wall. The numbers shown are the ones an investigator would ask for
 * on opening a case - what came in, what it resolved into, what the analysis
 * found, and where to start - and every one of them is read from the case.
 */

import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '../components/shell/AppShell.jsx'
import Icon, { entityIcon } from '../components/common/Icon.jsx'
import { Caveat, EntityChip, PanelSection, Stat } from '../components/common/Bits.jsx'
import { DataBoundary, EmptyState, ErrorState, Skeleton } from '../components/common/States.jsx'
import Timeline from '../components/timeline/Timeline.jsx'
import { useInvestigation } from '../state/InvestigationContext.jsx'
import {
  CASE_STATUS_LABEL,
  ENTITY_HEX,
  ENTITY_TYPES,
  LEAD_TYPE_LABEL,
  contextMeta,
  entityMeta,
  priorityMeta,
} from '../lib/domain.js'
import { caseShortName, formatDate, formatDateTime, plural } from '../lib/format.js'

function TypeBar({ counts, total }) {
  const present = ENTITY_TYPES.filter((type) => (counts[type] ?? 0) > 0)
  if (!total) return null
  return (
    <div className="typebar">
      <div className="typebar__track">
        {present.map((type) => (
          <span
            key={type}
            className="typebar__seg"
            style={{
              width: `${((counts[type] ?? 0) / total) * 100}%`,
              background: ENTITY_HEX[type],
            }}
            title={`${entityMeta(type).plural}: ${counts[type]}`}
          />
        ))}
      </div>
      <ul className="typebar__key">
        {present.map((type) => (
          <li key={type}>
            <span style={{ color: ENTITY_HEX[type], display: 'inline-flex' }}>
              <Icon name={entityIcon(type)} size={12} strokeWidth={1.5} />
            </span>
            <span className="typebar__name">{entityMeta(type).plural}</span>
            <span className="num typebar__count">{counts[type]}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ContextBar({ totals }) {
  const entries = Object.entries(totals ?? {}).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((sum, [, count]) => sum + count, 0)
  if (!total) return null
  return (
    <ul className="ctxlist">
      {entries.map(([context, count]) => (
        <li key={context}>
          <span className="ctxlist__label">
            <span
              className="ctxlist__dash"
              style={{ background: contextMeta(context).color }}
              aria-hidden="true"
            />
            {contextMeta(context).label}
          </span>
          <span className="ctxlist__track">
            <span
              className="ctxlist__fill"
              style={{ width: `${(count / total) * 100}%`, background: contextMeta(context).color }}
            />
          </span>
          <span className="num ctxlist__count">{count}</span>
        </li>
      ))}
    </ul>
  )
}

export function OverviewPage() {
  const { core, intel, index, selectEntity, reload } = useInvestigation()
  const navigate = useNavigate()
  const summary = core.data?.summary

  const typeCounts = useMemo(() => {
    const counts = {}
    for (const entity of index.entities) counts[entity.entity_type] = (counts[entity.entity_type] ?? 0) + 1
    return counts
  }, [index.entities])

  const leads = intel.data?.leads?.leads ?? []
  const topLeads = leads.slice(0, 3)
  const anomalies = intel.data?.anomalies
  const communities = intel.data?.communities
  const runs = core.data?.runs?.runs ?? []
  const documents = core.data?.documents?.documents ?? []

  const openEntity = (entityId) => {
    selectEntity(entityId, 'overview')
    navigate('/network')
  }

  if (core.status === 'error') {
    return (
      <>
        <PageHeader title="Overview" />
        <div className="page">
          <ErrorState error={core.error} onRetry={reload} />
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={summary ? caseShortName(summary.case_id) : 'Investigation'}
        meta={
          summary ? (
            <>
              <span className="mono" style={{ color: 'var(--text-muted)' }}>
                {summary.case_id}
              </span>
              <span className="pill pill--square pill--medium">
                {CASE_STATUS_LABEL[summary.status] ?? summary.status}
              </span>
            </>
          ) : null
        }
        description={summary?.description}
        actions={
          <Link to="/network" className="btn btn--primary">
            <Icon name="network" size={13} />
            Open network
          </Link>
        }
      />

      <div className="page">
        <DataBoundary
          status={core.status}
          error={core.error}
          isEmpty={false}
          onRetry={reload}
          skeleton={<Skeleton rows={5} height={64} />}
        >
          <div className="ovgrid">
            <section className="card card--span2">
              <PanelSection title="What this case holds">
                <div className="ovstats">
                  <Stat label="Documents" value={summary?.document_count ?? 0} />
                  <Stat label="Records" value={summary?.record_count ?? 0} />
                  <Stat label="Entities" value={summary?.entity_count ?? 0} />
                  <Stat label="Relationships" value={summary?.relationship_count ?? 0} />
                  <Stat label="Evidence rows" value={index.counts.evidence} />
                  <Stat label="Pipeline runs" value={summary?.run_count ?? 0} />
                </div>
                <p className="ovnote">
                  Records are authoritative; entities, relationships and the graph are rebuilt from
                  them on every run, which is why a person named in a second document merges with
                  the first rather than doubling.
                </p>
              </PanelSection>
            </section>

            <section className="card">
              <PanelSection title="Entity composition" count={index.counts.entities}>
                <TypeBar counts={typeCounts} total={index.counts.entities} />
              </PanelSection>
            </section>

            <section className="card">
              <PanelSection title="Relationship context" count={index.counts.relationships}>
                {intel.status === 'loading' ? (
                  <Skeleton rows={4} height={16} />
                ) : (
                  <ContextBar totals={intel.data?.relationshipContext?.context_totals} />
                )}
              </PanelSection>
            </section>

            <section className="card card--span2">
              <PanelSection
                title="Recorded activity"
                action={
                  <Link to="/timeline" className="btn btn--ghost btn--sm">
                    Timeline
                    <Icon name="chevronRight" size={11} />
                  </Link>
                }
              >
                <Timeline
                  index={index}
                  timeRange={null}
                  setTimeRange={() => {}}
                  selection={null}
                  onSelectRelationship={() => {}}
                  height={96}
                />
              </PanelSection>
            </section>

            <section className="card card--span2">
              <PanelSection
                title="Investigative leads"
                count={leads.length}
                action={
                  <Link to="/leads" className="btn btn--ghost btn--sm">
                    All leads
                    <Icon name="chevronRight" size={11} />
                  </Link>
                }
              >
                {intel.status === 'loading' ? (
                  <Skeleton rows={3} height={54} />
                ) : intel.status === 'error' ? (
                  <ErrorState error={intel.error} compact />
                ) : topLeads.length === 0 ? (
                  <EmptyState
                    icon="leads"
                    title="No leads raised for this investigation"
                    detail="Stage C found no pattern in this case that clears its thresholds. For an ordinary network that is the expected result."
                  />
                ) : (
                  <ul className="leadstrip">
                    {topLeads.map((lead) => (
                      <li key={lead.lead_id}>
                        <button
                          type="button"
                          className="leadcard leadcard--compact"
                          onClick={() => openEntity(lead.subject_entity_ids[0])}
                        >
                          <span className="leadcard__top">
                            <span className={`pill ${priorityMeta(lead.network_priority).pill}`}>
                              {priorityMeta(lead.network_priority).label}
                            </span>
                            <span className="leadcard__type">
                              {LEAD_TYPE_LABEL[lead.lead_type] ?? lead.lead_type}
                            </span>
                          </span>
                          <span className="leadcard__subject">{lead.subject_labels.join(', ')}</span>
                          <span className="leadcard__why">
                            {lead.signal_count} signals across {lead.independent_category_count}{' '}
                            independent categories · {lead.evidence_ids.length} evidence
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </PanelSection>
            </section>

            <section className="card">
              <PanelSection title="Analytical signals" count={anomalies?.count ?? 0}>
                {intel.status === 'loading' ? (
                  <Skeleton rows={3} height={22} />
                ) : (
                  <>
                    <div className="ovstats ovstats--tight">
                      <Stat label="Signals" value={anomalies?.count ?? 0} />
                      <Stat label="Detectors run" value={anomalies?.detectors_run?.length ?? 0} />
                      <Stat label="Clusters" value={communities?.count ?? 0} />
                    </div>
                    {anomalies?.detectors_skipped &&
                    Object.keys(anomalies.detectors_skipped).length ? (
                      <p className="ovnote">
                        Skipped:{' '}
                        {Object.keys(anomalies.detectors_skipped)
                          .map((name) => name.replace(/_/g, ' '))
                          .join(', ')}
                        .
                      </p>
                    ) : null}
                    <Link to="/analytics" className="btn btn--sm">
                      Open analytics
                      <Icon name="chevronRight" size={11} />
                    </Link>
                  </>
                )}
              </PanelSection>
            </section>

            <section className="card">
              <PanelSection title="Sources" count={documents.length}>
                {documents.length === 0 ? (
                  <EmptyState icon="document" title="No documents recorded" />
                ) : (
                  <ul className="sourcelist">
                    {documents.slice(0, 4).map((document) => (
                      <li key={document.document_id}>
                        <Link to="/evidence" className="sourcerow">
                          <Icon name="document" size={13} />
                          <span className="sourcerow__title truncate">{document.title ?? document.document_id}</span>
                          <span className="sourcerow__meta mono">
                            {formatDate(document.collected_at)}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
                {runs.length ? (
                  <p className="ovnote">
                    Last run {runs[runs.length - 1].kind} · {runs[runs.length - 1].status} ·{' '}
                    {formatDateTime(runs[runs.length - 1].completed_at ?? runs[runs.length - 1].started_at)}
                  </p>
                ) : null}
              </PanelSection>
            </section>

            <section className="card card--span2">
              <Caveat>
                Silent Trace is decision support over synthetic records. Analytical signals describe
                structure and timing in a graph; they are never evidence of wrongdoing, and network
                position says nothing about conduct.
              </Caveat>
            </section>
          </div>
        </DataBoundary>
      </div>
    </>
  )
}

export default OverviewPage
