/*
 * Stage C, exposed.
 *
 * Compact analytical readouts rather than executive tiles: a ranking you can
 * re-metric, the clusters the graph decomposes into, the entities sitting
 * between them, and the raw signals with the explanation each detector wrote.
 * Every panel carries the backend's own caveat, unedited.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../components/shell/AppShell.jsx'
import Icon, { entityIcon } from '../components/common/Icon.jsx'
import { Caveat, EntityChip, Meter, PanelSection } from '../components/common/Bits.jsx'
import { DataBoundary, EmptyState, ErrorState, Skeleton } from '../components/common/States.jsx'
import ContextDrawer from '../components/panels/ContextDrawer.jsx'
import { useInvestigation } from '../state/InvestigationContext.jsx'
import { api } from '../api/endpoints.js'
import {
  ANOMALY_TYPE_LABEL,
  CATEGORY_LABEL,
  CENTRALITY_METRICS,
  ENTITY_HEX,
  INDICATOR_TYPE_LABEL,
  contextMeta,
} from '../lib/domain.js'
import { formatNumber, formatPercent, plural } from '../lib/format.js'

function CentralityPanel({ caseId, index, onSelect }) {
  const [metric, setMetric] = useState('degree')
  const [state, setState] = useState({ status: 'loading', data: null, error: null })

  useEffect(() => {
    let live = true
    setState({ status: 'loading', data: null, error: null })
    api
      .centrality(caseId, metric, 12)
      .then((data) => live && setState({ status: 'ready', data, error: null }))
      .catch((error) => live && setState({ status: 'error', data: null, error }))
    return () => {
      live = false
    }
  }, [caseId, metric])

  const scores = state.data?.scores ?? []
  const peak = Math.max(1, ...scores.map((score) => score.value))
  const description = CENTRALITY_METRICS.find((item) => item.value === metric)?.blurb

  return (
    <section className="card">
      <PanelSection
        title="Centrality"
        action={
          <select
            className="select"
            value={metric}
            onChange={(event) => setMetric(event.target.value)}
            aria-label="Centrality metric"
            style={{ height: 24, fontSize: 11 }}
          >
            {CENTRALITY_METRICS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        }
      >
        <p className="hinttext">{description}</p>
        <DataBoundary
          status={state.status}
          error={state.error}
          isEmpty={scores.length === 0}
          skeleton={<Skeleton rows={5} height={22} />}
          empty={
            <EmptyState
              icon="analytics"
              title="Not enough graph to rank"
              detail={state.data?.reason ?? 'This case has too few relationships to compute a ranking.'}
            />
          }
        >
          <ul className="ranklist">
            {scores.map((score) => (
              <li key={score.entity_id}>
                <button type="button" className="rankrow" onClick={() => onSelect(score.entity_id)}>
                  <span className="rankrow__rank num">{score.rank}</span>
                  <span
                    className="rankrow__glyph"
                    style={{ color: ENTITY_HEX[score.entity_type] ?? 'var(--text-muted)' }}
                  >
                    <Icon name={entityIcon(score.entity_type)} size={12} strokeWidth={1.5} />
                  </span>
                  <span className="rankrow__label truncate">{score.label}</span>
                  <Meter
                    value={score.value / peak}
                    color={ENTITY_HEX[score.entity_type] ?? 'var(--ink)'}
                    width={56}
                  />
                  <span className="rankrow__value num">{formatNumber(score.value)}</span>
                </button>
              </li>
            ))}
          </ul>
        </DataBoundary>
        {state.data?.method ? <p className="methodnote mono">{state.data.method}</p> : null}
        {state.data?.caveat ? <Caveat>{state.data.caveat}</Caveat> : null}
      </PanelSection>
    </section>
  )
}

export function AnalyticsPage() {
  const { caseId, core, intel, index, selection, select, selectEntity, clearSelection, reload } =
    useInvestigation()
  const navigate = useNavigate()

  const communities = intel.data?.communities
  const bridges = intel.data?.bridges
  const anomalies = intel.data?.anomalies
  const indicators = intel.data?.indicators
  const relationshipContext = intel.data?.relationshipContext

  const openEntity = (entityId) => select('entity', entityId, 'analytics')

  if (intel.status === 'error') {
    return (
      <>
        <PageHeader title="Analytics" />
        <div className="page">
          <ErrorState error={intel.error} onRetry={reload} />
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Analytics"
        description="What the Stage C intelligence layer found in this graph, with the reasoning each analysis produced."
      />

      <div className="page splitpage">
        <div className="splitpage__main">
          <div className="anagrid">
            {caseId ? <CentralityPanel caseId={caseId} index={index} onSelect={openEntity} /> : null}

            <section className="card">
              <PanelSection title="Clusters" count={communities?.count ?? 0}>
                <DataBoundary
                  status={intel.status}
                  error={intel.error}
                  isEmpty={!communities?.communities?.length}
                  skeleton={<Skeleton rows={3} height={54} />}
                  empty={
                    <EmptyState
                      icon="community"
                      title="No community structure"
                      detail={communities?.reason ?? 'This graph does not decompose into clusters.'}
                    />
                  }
                >
                  <>
                    <p className="hinttext">
                      Modularity {formatNumber(communities?.modularity ?? 0)} ·{' '}
                      <span className="mono">{communities?.method}</span>
                    </p>
                    <ul className="cardlist">
                      {communities?.communities?.map((community) => (
                        <li key={community.community_id} className="commcard">
                          <div className="commcard__head">
                            <span className="mono commcard__id">{community.community_id}</span>
                            <span className="num">{plural(community.size, 'member')}</span>
                            <span className="commcard__density num">
                              {formatPercent(community.internal_density)} internal density
                            </span>
                          </div>
                          <div className="commcard__members">
                            {community.member_entity_ids.map((memberId) => (
                              <EntityChip
                                key={memberId}
                                size="sm"
                                entity={index.entityById.get(memberId)}
                                entityId={memberId}
                                label={index.labelOf(memberId)}
                                onSelect={openEntity}
                              />
                            ))}
                          </div>
                          <p className="commcard__note">{community.explanation}</p>
                          <div className="commcard__contexts">
                            {community.dominant_contexts.map((context) => (
                              <span key={context} className="ctag">
                                <span
                                  className="ctag__dash"
                                  style={{ background: contextMeta(context).color }}
                                />
                                {contextMeta(context).label}
                              </span>
                            ))}
                          </div>
                        </li>
                      ))}
                    </ul>
                    {communities?.caveat ? <Caveat>{communities.caveat}</Caveat> : null}
                  </>
                </DataBoundary>
              </PanelSection>
            </section>

            <section className="card">
              <PanelSection title="Potential bridges" count={bridges?.count ?? 0}>
                <DataBoundary
                  status={intel.status}
                  error={intel.error}
                  isEmpty={!bridges?.bridges?.length}
                  skeleton={<Skeleton rows={3} height={44} />}
                  empty={
                    <EmptyState
                      icon="link"
                      title="No intermediary position found"
                      detail={
                        bridges?.reason ??
                        'Every route in this graph has an equally short alternative, so no entity sits between clusters.'
                      }
                    />
                  }
                >
                  <>
                    <ul className="cardlist">
                      {bridges?.bridges?.map((bridge) => (
                        <li key={bridge.entity_id}>
                          <button
                            type="button"
                            className="bridgecard"
                            onClick={() => openEntity(bridge.entity_id)}
                          >
                            <span className="bridgecard__head">
                              <span
                                style={{ color: ENTITY_HEX[bridge.entity_type], display: 'inline-flex' }}
                              >
                                <Icon name={entityIcon(bridge.entity_type)} size={13} strokeWidth={1.5} />
                              </span>
                              <strong>{bridge.label}</strong>
                              <span className="bridgecard__comms mono">
                                {bridge.connected_community_ids.join(' ↔ ')}
                              </span>
                            </span>
                            <span className="bridgecard__bar">
                              <Meter
                                value={bridge.normalized_betweenness}
                                color="var(--e-vehicle)"
                                width={90}
                              />
                              <span className="num">
                                {formatPercent(bridge.normalized_betweenness)} normalised betweenness
                              </span>
                            </span>
                            <span className="bridgecard__note">{bridge.explanation}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                    {bridges?.caveat ? <Caveat>{bridges.caveat}</Caveat> : null}
                  </>
                </DataBoundary>
              </PanelSection>
            </section>

            <section className="card">
              <PanelSection title="Anomaly signals" count={anomalies?.count ?? 0}>
                <DataBoundary
                  status={intel.status}
                  error={intel.error}
                  isEmpty={!anomalies?.signals?.length}
                  skeleton={<Skeleton rows={4} height={38} />}
                  empty={
                    <EmptyState
                      icon="spark"
                      title="No signal differs from the rest of this case"
                      detail="Every detector ran and found nothing standing out. For an ordinary network that is the expected result."
                    />
                  }
                >
                  <>
                    <ul className="signallist">
                      {anomalies?.signals?.map((signal) => (
                        <li key={signal.signal_id}>
                          <button
                            type="button"
                            className="signalrow"
                            onClick={() => openEntity(signal.entity_id)}
                          >
                            <span className="signalrow__top">
                              <span className="signalrow__type">
                                {ANOMALY_TYPE_LABEL[signal.anomaly_type] ?? signal.anomaly_type}
                              </span>
                              <span className="pill pill--square">
                                {CATEGORY_LABEL[signal.category] ?? signal.category}
                              </span>
                              <span className="signalrow__strength">
                                <Meter
                                  value={signal.signal_strength}
                                  color="var(--priority-high)"
                                  width={44}
                                />
                                <span className="num">{formatPercent(signal.signal_strength)}</span>
                              </span>
                            </span>
                            <span className="signalrow__subject">{signal.label}</span>
                            <span className="signalrow__note">{signal.explanation}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                    <p className="methodnote">
                      Detectors run: {anomalies?.detectors_run?.join(', ').replace(/_/g, ' ')}
                      {anomalies?.detectors_skipped &&
                      Object.keys(anomalies.detectors_skipped).length ? (
                        <>
                          {' · skipped: '}
                          {Object.entries(anomalies.detectors_skipped)
                            .map(([name]) => name.replace(/_/g, ' '))
                            .join(', ')}
                        </>
                      ) : null}
                    </p>
                    {anomalies?.caveat ? <Caveat>{anomalies.caveat}</Caveat> : null}
                  </>
                </DataBoundary>
              </PanelSection>
            </section>

            <section className="card">
              <PanelSection title="Activity indicators" count={indicators?.count ?? 0}>
                <DataBoundary
                  status={intel.status}
                  error={intel.error}
                  isEmpty={!indicators?.indicators?.length}
                  skeleton={<Skeleton rows={3} height={38} />}
                  empty={<EmptyState icon="target" title="No structural indicator raised" />}
                >
                  <>
                    <ul className="signallist">
                      {indicators?.indicators?.map((indicator) => (
                        <li key={indicator.indicator_id}>
                          <button
                            type="button"
                            className="signalrow"
                            onClick={() => openEntity(indicator.entity_ids[0])}
                          >
                            <span className="signalrow__top">
                              <span className="signalrow__type">
                                {INDICATOR_TYPE_LABEL[indicator.indicator_type] ??
                                  indicator.indicator_type}
                              </span>
                              <span className="signalrow__strength">
                                <Meter value={indicator.confidence} color="var(--e-incident)" width={44} />
                                <span className="num">{formatPercent(indicator.confidence)}</span>
                              </span>
                            </span>
                            <span className="signalrow__subject">{indicator.labels.join(' · ')}</span>
                            <span className="signalrow__note">{indicator.explanation}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                    {indicators?.caveat ? <Caveat>{indicators.caveat}</Caveat> : null}
                  </>
                </DataBoundary>
              </PanelSection>
            </section>

            <section className="card">
              <PanelSection title="Relationship contexts" count={relationshipContext?.count ?? 0}>
                <DataBoundary
                  status={intel.status}
                  error={intel.error}
                  isEmpty={!relationshipContext?.count}
                  skeleton={<Skeleton rows={4} height={18} />}
                  empty={<EmptyState icon="link" title="No relationships to classify" />}
                >
                  <>
                    <ul className="ctxlist">
                      {Object.entries(relationshipContext?.context_totals ?? {})
                        .sort((a, b) => b[1] - a[1])
                        .map(([context, count]) => (
                          <li key={context}>
                            <span className="ctxlist__label">
                              <span
                                className="ctxlist__dash"
                                style={{ background: contextMeta(context).color }}
                              />
                              {contextMeta(context).label}
                            </span>
                            <span className="ctxlist__track">
                              <span
                                className="ctxlist__fill"
                                style={{
                                  width: `${(count / (relationshipContext?.count || 1)) * 100}%`,
                                  background: contextMeta(context).color,
                                }}
                              />
                            </span>
                            <span className="num ctxlist__count">{count}</span>
                          </li>
                        ))}
                    </ul>
                    {relationshipContext?.caveat ? <Caveat>{relationshipContext.caveat}</Caveat> : null}
                  </>
                </DataBoundary>
              </PanelSection>
            </section>
          </div>
        </div>

        {selection.kind ? (
          <div className="splitpage__side">
            <ContextDrawer
              inline
              selection={selection}
              index={index}
              intel={intel.data}
              onClose={clearSelection}
              onSelectEntity={(id) => select('entity', id, 'analytics')}
              onSelectRelationship={(id) => select('relationship', id, 'analytics')}
              onOpenEvidence={(id) => select('evidence', id, 'analytics')}
              onTraceFrom={(id) => {
                selectEntity(id, 'analytics')
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

export default AnalyticsPage
