/*
 * The temporal view.
 *
 * Same relationships, addressed by when they happened. Selecting a window here
 * narrows the graph everywhere else, and the window analysis is computed from
 * the relationships that actually fall inside it.
 */

import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../components/shell/AppShell.jsx'
import Icon from '../components/common/Icon.jsx'
import { Caveat, EntityChip, PanelSection, Stat } from '../components/common/Bits.jsx'
import { DataBoundary, EmptyState } from '../components/common/States.jsx'
import Timeline, { EventList } from '../components/timeline/Timeline.jsx'
import TraceAnalysis from '../components/panels/TraceAnalysis.jsx'
import ContextDrawer from '../components/panels/ContextDrawer.jsx'
import { useInvestigation } from '../state/InvestigationContext.jsx'
import { analyseWindow } from '../lib/traceAnalysis.js'
import { formatDate, plural } from '../lib/format.js'

export function TimelinePage() {
  const {
    core,
    intel,
    index,
    selection,
    select,
    selectEntity,
    clearSelection,
    timeRange,
    setTimeRange,
    reload,
  } = useInvestigation()
  const navigate = useNavigate()

  const analysis = useMemo(
    () => (timeRange ? analyseWindow(timeRange, index) : null),
    [timeRange, index],
  )

  const inWindow = timeRange
    ? index.events.filter((event) => event.at >= timeRange[0] && event.at <= timeRange[1])
    : index.events

  const temporalProfiles = intel.data?.temporal?.profiles ?? []

  return (
    <>
      <PageHeader
        title="Timeline"
        description="When the recorded relationships in this case happened, and what changes across a window."
        actions={
          timeRange ? (
            <button type="button" className="btn" onClick={() => setTimeRange(null)}>
              <Icon name="close" size={12} />
              Clear window
            </button>
          ) : null
        }
      />

      <div className="page splitpage">
        <div className="splitpage__main">
          <DataBoundary
            status={core.status}
            error={core.error}
            isEmpty={index.events.length === 0}
            onRetry={reload}
            empty={
              <EmptyState
                icon="clock"
                title="Nothing in this case carries a timestamp"
                detail="Relationships gain a place on the timeline when a source states when they occurred."
              />
            }
          >
            <>
              <section className="card">
                <PanelSection
                  title={
                    timeRange
                      ? `Window · ${formatDate(timeRange[0])} – ${formatDate(timeRange[1])}`
                      : 'Full recorded period'
                  }
                  count={inWindow.length}
                >
                  <Timeline
                    index={index}
                    timeRange={timeRange}
                    setTimeRange={setTimeRange}
                    selection={selection}
                    onSelectRelationship={(id) => select('relationship', id, 'timeline')}
                    height={140}
                  />
                  <p className="hinttext">
                    Drag across the axis to select a window. The graph, and every other surface,
                    narrows with it. Bars in{' '}
                    <span style={{ color: 'var(--trace)', fontWeight: 600 }}>ochre</span> are the
                    relationships attached to the current selection.
                  </p>
                </PanelSection>
              </section>

              {analysis ? (
                <section className="card">
                  <TraceAnalysis
                    analysis={analysis}
                    index={index}
                    onOpenEvidence={(id) => select('evidence', id, 'timeline')}
                    onSelectRelationship={(id) => select('relationship', id, 'timeline')}
                  />
                  {analysis.busiest?.length ? (
                    <div className="windowbusy">
                      <p className="eyebrow">Most active in this window</p>
                      <div className="windowbusy__row">
                        {analysis.busiest.map((item) => (
                          <span key={item.entityId} className="windowbusy__item">
                            <EntityChip
                              size="sm"
                              entity={index.entityById.get(item.entityId)}
                              entityId={item.entityId}
                              label={item.label}
                              onSelect={(id) => select('entity', id, 'timeline')}
                            />
                            <span className="num">{item.count}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>
              ) : null}

              <section className="card">
                <PanelSection title="Recorded relationships" count={inWindow.length}>
                  <EventList
                    index={index}
                    timeRange={timeRange}
                    selection={selection}
                    onSelectRelationship={(id) => select('relationship', id, 'timeline')}
                  />
                </PanelSection>
              </section>

              {temporalProfiles.length ? (
                <section className="card">
                  <PanelSection title="Temporal profiles" count={temporalProfiles.length}>
                    <ul className="profilelist">
                      {temporalProfiles.slice(0, 6).map((profile) => (
                        <li key={profile.entity_id}>
                          <button
                            type="button"
                            className="profilerow"
                            onClick={() => select('entity', profile.entity_id, 'timeline')}
                          >
                            <span className="profilerow__head">
                              <strong>{profile.label}</strong>
                              <span className="num profilerow__count">
                                {plural(profile.event_count, 'event')}
                              </span>
                            </span>
                            <span className="profilerow__spark">
                              {profile.buckets.map((bucket) => (
                                <span
                                  key={bucket.period_start}
                                  className="profilerow__bar"
                                  style={{
                                    height: `${Math.max(
                                      12,
                                      (bucket.event_count / Math.max(1, profile.peak_event_count)) *
                                        100,
                                    )}%`,
                                  }}
                                  title={`${formatDate(bucket.period_start)}: ${plural(
                                    bucket.event_count,
                                    'relationship',
                                  )}`}
                                />
                              ))}
                            </span>
                            <span className="profilerow__note">{profile.explanation}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </PanelSection>
                </section>
              ) : null}

              <Caveat>
                A busier period means more source records carry timestamps there. Recording density
                is a property of the sources, not of the people in them.
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
              onSelectEntity={(id) => select('entity', id, 'timeline')}
              onSelectRelationship={(id) => select('relationship', id, 'timeline')}
              onOpenEvidence={(id) => select('evidence', id, 'timeline')}
              onTraceFrom={(id) => {
                selectEntity(id, 'timeline')
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

export default TimelinePage
