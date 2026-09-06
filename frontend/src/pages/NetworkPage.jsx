/*
 * The network workspace - the page the rest of the product orbits.
 *
 * The canvas gets the space. Controls sit in one compact bar above it, the
 * temporal dimension docks below it, and the contextual panel exists only while
 * something is selected. Selecting on the canvas updates the panel and the
 * timeline; selecting in the panel or the timeline updates the canvas.
 */

import { useCallback, useMemo, useRef, useState } from 'react'
import { PageHeader } from '../components/shell/AppShell.jsx'
import NetworkGraph from '../components/graph/NetworkGraph.jsx'
import { GraphLegend, GraphToolbar } from '../components/graph/GraphToolbar.jsx'
import ContextDrawer from '../components/panels/ContextDrawer.jsx'
import CreateConnectionDialog from '../components/panels/CreateConnectionDialog.jsx'
import Timeline from '../components/timeline/Timeline.jsx'
import Icon from '../components/common/Icon.jsx'
import { ErrorState, Skeleton } from '../components/common/States.jsx'
import { useInvestigation } from '../state/InvestigationContext.jsx'
import { CASE_STATUS_LABEL } from '../lib/domain.js'
import { caseShortName, formatDate, plural } from '../lib/format.js'

export function NetworkPage() {
  const {
    core,
    intel,
    index,
    selection,
    select,
    selectEntity,
    clearSelection,
    filters,
    setFilters,
    timeRange,
    setTimeRange,
    trace,
    setTrace,
    runTrace,
    clearTrace,
    clearPaths,
    pathResult,
    activePath,
    activePathIndex,
    setActivePathIndex,
    focusToken,
    createRelationship,
    reload,
  } = useInvestigation()

  const cyRef = useRef(null)
  const [layoutName, setLayoutName] = useState('fcose')
  const [legendOpen, setLegendOpen] = useState(true)
  const [connectFrom, setConnectFrom] = useState(undefined)

  const summary = core.data?.summary

  const typeCounts = useMemo(() => {
    const counts = {}
    for (const entity of index.entities) {
      counts[entity.entity_type] = (counts[entity.entity_type] ?? 0) + 1
    }
    return counts
  }, [index.entities])

  const contextCounts = intel.data?.relationshipContext?.context_totals

  /* Clicking a node means different things depending on the mode the toolbar is
   * in, so the two behaviours are resolved here rather than inside the canvas. */
  const handleNodeTap = useCallback(
    (entityId) => {
      if (!trace.active) {
        selectEntity(entityId, 'graph')
        return
      }
      /* First click picks the source, second the target. Clicking again once a
       * pair is complete starts a fresh trace from the entity just clicked. */
      const startingOver = !trace.source || (trace.source && trace.target)
      if (startingOver) {
        setTrace((current) => ({ ...current, source: entityId, target: null }))
        clearPaths()
      } else if (trace.source !== entityId) {
        setTrace((current) => ({ ...current, target: entityId }))
        runTrace(trace.source, entityId, trace.maxDepth)
      }
      select('path', 'trace', 'graph')
    },
    [clearPaths, runTrace, select, selectEntity, setTrace, trace],
  )

  const openEvidence = useCallback((provenanceId) => select('evidence', provenanceId, 'panel'), [select])
  const openRelationship = useCallback(
    (relationshipId) => select('relationship', relationshipId, 'panel'),
    [select],
  )

  const startTraceFrom = useCallback(
    (entityId) => {
      setTrace({ active: true, source: entityId, target: null, maxDepth: trace.maxDepth })
      select('path', 'trace', 'inspector')
    },
    [select, setTrace, trace.maxDepth],
  )

  const changeDepth = useCallback(
    (depth) => {
      setTrace((current) => {
        if (current.source && current.target) runTrace(current.source, current.target, depth)
        return { ...current, maxDepth: depth }
      })
    },
    [runTrace, setTrace],
  )

  const resetTrace = useCallback(() => {
    clearTrace()
    setTrace((current) => ({ ...current, source: null, target: null }))
    if (selection.kind === 'path') clearSelection()
  }, [clearSelection, clearTrace, selection.kind, setTrace])

  const fit = useCallback(() => cyRef.current?.animate({ fit: { padding: 56 } }, { duration: 260 }), [])
  const zoom = useCallback((factor) => {
    const cy = cyRef.current
    if (!cy) return
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  }, [])

  if (core.status === 'error') {
    return (
      <>
        <PageHeader title="Network" />
        <div className="page">
          <ErrorState error={core.error} onRetry={reload} />
        </div>
      </>
    )
  }

  const tracePrompt = trace.active
    ? !trace.source
      ? 'Click the first entity to trace from'
      : !trace.target
        ? 'Click the second entity to trace to'
        : null
    : null

  return (
    <>
      <PageHeader
        title={summary ? caseShortName(summary.case_id) : 'Network'}
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
          <span className="headcounts">
            <span>
              <strong className="num">{index.counts.entities}</strong> entities
            </span>
            <span>
              <strong className="num">{index.counts.relationships}</strong> relationships
            </span>
            <span>
              <strong className="num">{index.counts.evidence}</strong> evidence
            </span>
          </span>
        }
      />

      <GraphToolbar
        filters={filters}
        setFilters={setFilters}
        layoutName={layoutName}
        setLayoutName={setLayoutName}
        contextCounts={contextCounts}
        onFit={fit}
        onZoom={zoom}
        trace={trace}
        setTrace={setTrace}
        onClearTrace={resetTrace}
        hasTrace={Boolean(trace.source || trace.target)}
        onCreateConnection={() => setConnectFrom(null)}
      />

      <div className="graphstage">
        {core.status === 'ready' && index.entities.length > 0 ? (
          <NetworkGraph
            index={index}
            selection={selection}
            onSelectEntity={handleNodeTap}
            onSelectRelationship={(id) => select('relationship', id, 'graph')}
            onClearSelection={() => {
              if (!trace.active) clearSelection()
            }}
            filters={filters}
            timeRange={timeRange}
            activePath={activePath}
            traceEndpoints={[trace.source, trace.target]}
            traceActive={trace.active}
            layoutName={layoutName}
            focusToken={focusToken}
            onReady={(cy) => {
              cyRef.current = cy
            }}
          />
        ) : null}

        {core.status !== 'ready' ? (
          <div className="goverlay">
            <div style={{ width: 320 }}>
              <Skeleton rows={3} height={40} />
              <p
                style={{
                  marginTop: 10,
                  textAlign: 'center',
                  fontSize: 11.5,
                  color: 'var(--text-muted)',
                }}
              >
                Loading the persisted graph for this investigation…
              </p>
            </div>
          </div>
        ) : null}

        {core.status === 'ready' && index.entities.length === 0 ? (
          <div className="goverlay">
            <div className="state state--empty">
              <Icon name="network" size={20} />
              <p className="state__title">This investigation has no entities yet</p>
              <p className="state__detail">
                The case exists but nothing has been ingested into it. Seed it from the backend
                with <span className="mono">python -m app.cli seed-demo</span>.
              </p>
            </div>
          </div>
        ) : null}

        {tracePrompt ? (
          <div className="gprompt">
            <Icon name="trace" size={13} />
            {tracePrompt}
          </div>
        ) : null}

        {core.status === 'ready' && index.entities.length > 0 ? (
          <>
            <div className="gstatus">
              <strong className="num">{index.counts.entities}</strong> nodes
              <span aria-hidden="true">·</span>
              <strong className="num">{index.counts.relationships}</strong> edges
              {timeRange ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span style={{ color: 'var(--trace)' }}>windowed</span>
                </>
              ) : null}
            </div>
            <GraphLegend
              counts={typeCounts}
              collapsed={!legendOpen}
              onToggle={() => setLegendOpen((value) => !value)}
            />
          </>
        ) : null}

        <ContextDrawer
          selection={selection}
          index={index}
          intel={intel.data}
          onClose={() => {
            if (selection.kind === 'path') resetTrace()
            else clearSelection()
          }}
          onSelectEntity={(id) => selectEntity(id, 'panel')}
          onSelectRelationship={openRelationship}
          onOpenEvidence={openEvidence}
          onTraceFrom={startTraceFrom}
          onCreateConnection={(entityId) => setConnectFrom(entityId)}
          pathProps={{
            trace,
            pathResult,
            activePath,
            activePathIndex,
            setActivePathIndex,
            onSelectEntity: (id) => selectEntity(id, 'path'),
            onSelectRelationship: openRelationship,
            onOpenEvidence: openEvidence,
            onChangeDepth: changeDepth,
            onClear: resetTrace,
          }}
        />
      </div>

      <div className="timelinedock">
        <div className="timelinedock__head">
          <span className="timelinedock__title">Activity</span>
          {timeRange ? (
            <span className="timelinedock__range">
              <Icon name="clock" size={11} />
              {formatDate(timeRange[0])} – {formatDate(timeRange[1])}
              <button
                type="button"
                className="btn btn--ghost btn--icon btn--sm"
                onClick={() => setTimeRange(null)}
                aria-label="Clear time window"
              >
                <Icon name="close" size={10} />
              </button>
            </span>
          ) : null}
          <span className="timelinedock__spacer" />
          <span className="timelinedock__hint">
            {timeRange
              ? 'Relationships outside the window are dimmed on the canvas'
              : 'Drag across the axis to narrow the graph to a time window'}
          </span>
        </div>
        <Timeline
          index={index}
          timeRange={timeRange}
          setTimeRange={setTimeRange}
          selection={selection}
          onSelectRelationship={openRelationship}
          height={78}
        />
      </div>

      {connectFrom !== undefined ? (
        <CreateConnectionDialog
          index={index}
          initialSource={connectFrom}
          onClose={() => setConnectFrom(undefined)}
          onCreate={async (body) => {
            const created = await createRelationship(body)
            select('relationship', created.relationship_id, 'analyst')
          }}
        />
      ) : null}
    </>
  )
}

export default NetworkPage
