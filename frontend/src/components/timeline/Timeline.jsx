/*
 * The temporal dimension of the investigation.
 *
 * Time here is not a separate chart; it is a second way of addressing the same
 * relationships. A bar is the relationships whose recorded timestamp falls in
 * that period, dragging across the axis narrows the graph to a window, and a
 * click selects a period so the rest of the workspace can respond to it.
 *
 * Nothing here reprojects the graph through time - the backend does not model
 * entity state over time and inventing that would be a lie. What it does is
 * honest: relationships outside the window recede on the canvas and everything
 * inside it stays fully drawn.
 */

import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import Icon from '../common/Icon.jsx'
import { EmptyState } from '../common/States.jsx'
import { formatDate, formatDayMonth, plural } from '../../lib/format.js'
import { ENTITY_HEX, contextMeta } from '../../lib/domain.js'
import './timeline.css'

const DAY = 86400000

function bucketise(events, extent) {
  if (!events.length || !extent) return { buckets: [], step: DAY, unit: 'day' }
  const [start, end] = extent
  const span = Math.max(DAY, end.getTime() - start.getTime())
  /* Keep the axis readable: switch to weeks rather than drawing 300 hairlines. */
  const step = span / DAY > 90 ? DAY * 7 : DAY
  const unit = step === DAY ? 'day' : 'week'
  const origin = Math.floor(start.getTime() / step) * step
  const count = Math.max(1, Math.ceil((end.getTime() - origin) / step) + 1)

  const buckets = Array.from({ length: count }, (_, position) => ({
    start: new Date(origin + position * step),
    end: new Date(origin + (position + 1) * step),
    events: [],
  }))

  for (const event of events) {
    const position = Math.min(
      count - 1,
      Math.max(0, Math.floor((event.at.getTime() - origin) / step)),
    )
    buckets[position].events.push(event)
  }
  return { buckets, step, unit }
}

export function Timeline({
  index,
  timeRange,
  setTimeRange,
  selection,
  onSelectRelationship,
  onSelectWindow,
  height = 92,
  showAxisLabels = true,
}) {
  const wrapRef = useRef(null)
  const [width, setWidth] = useState(720)
  const [drag, setDrag] = useState(null)
  const [hoverBucket, setHoverBucket] = useState(null)

  useLayoutEffect(() => {
    const element = wrapRef.current
    if (!element) return undefined
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect?.width
      if (next) setWidth(next)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const { buckets, unit } = useMemo(
    () => bucketise(index.events, index.timeExtent),
    [index.events, index.timeExtent],
  )

  const peak = Math.max(1, ...buckets.map((bucket) => bucket.events.length))
  const extent = index.timeExtent

  /* Relationships attached to whatever is currently selected, so the timeline
   * answers "when did this happen" for the selection without a second query. */
  const highlighted = useMemo(() => {
    if (!selection?.id) return null
    if (selection.kind === 'entity') {
      return new Set(
        (index.edgesByEntity.get(selection.id) ?? []).map((r) => r.relationship_id),
      )
    }
    if (selection.kind === 'relationship') return new Set([selection.id])
    return null
  }, [selection, index])

  const toX = useCallback(
    (index_) => (buckets.length <= 1 ? 0 : (index_ / buckets.length) * width),
    [buckets.length, width],
  )
  const slot = buckets.length ? width / buckets.length : 0
  const bandWidth = buckets.length ? Math.min(22, Math.max(2, slot - 1.4)) : 0
  const bandOffset = Math.max(0, (slot - bandWidth) / 2)

  const bucketAt = useCallback(
    (clientX) => {
      const rect = wrapRef.current?.getBoundingClientRect()
      if (!rect || !buckets.length) return 0
      const ratio = (clientX - rect.left) / rect.width
      return Math.min(buckets.length - 1, Math.max(0, Math.floor(ratio * buckets.length)))
    },
    [buckets.length],
  )

  const onPointerDown = (event) => {
    if (!buckets.length) return
    event.currentTarget.setPointerCapture?.(event.pointerId)
    const position = bucketAt(event.clientX)
    setDrag({ from: position, to: position, moved: false })
  }

  const onPointerMove = (event) => {
    const position = bucketAt(event.clientX)
    setHoverBucket(position)
    if (!drag) return
    setDrag((current) =>
      current ? { ...current, to: position, moved: current.moved || position !== current.from } : current,
    )
  }

  const onPointerUp = () => {
    if (!drag) return
    const lo = Math.min(drag.from, drag.to)
    const hi = Math.max(drag.from, drag.to)
    const from = buckets[lo]?.start
    const to = buckets[hi]?.end
    if (from && to) {
      setTimeRange([from, to])
      onSelectWindow?.([from, to])
    }
    setDrag(null)
  }

  if (!buckets.length) {
    return (
      <div className="timeline timeline--empty" style={{ height }}>
        <EmptyState
          icon="clock"
          title="No timestamped relationships"
          detail="No relationship in this case states when it occurred, so there is no timeline to draw."
        />
      </div>
    )
  }

  const selectionBand = (() => {
    if (drag) {
      const lo = Math.min(drag.from, drag.to)
      const hi = Math.max(drag.from, drag.to)
      return { x: toX(lo), width: Math.max(bandWidth, toX(hi + 1) - toX(lo)) }
    }
    if (!timeRange) return null
    const lo = buckets.findIndex((bucket) => bucket.end > timeRange[0])
    let hi = buckets.length - 1
    for (let position = buckets.length - 1; position >= 0; position -= 1) {
      if (buckets[position].start < timeRange[1]) {
        hi = position
        break
      }
    }
    if (lo < 0) return null
    return { x: toX(lo), width: Math.max(bandWidth, toX(hi + 1) - toX(lo)) }
  })()

  const plotHeight = height - (showAxisLabels ? 18 : 6)
  const hovered = hoverBucket !== null ? buckets[hoverBucket] : null

  return (
    <div className="timeline" style={{ height }}>
      <div
        className="timeline__plot"
        ref={wrapRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => setHoverBucket(null)}
        role="group"
        aria-label="Activity over time. Drag to select a window."
      >
        <svg width={width} height={plotHeight} className="timeline__svg">
          {[0.25, 0.5, 0.75, 1].map((line) => (
            <line
              key={line}
              x1={0}
              x2={width}
              y1={plotHeight - line * (plotHeight - 6)}
              y2={plotHeight - line * (plotHeight - 6)}
              stroke="var(--grid)"
              strokeWidth={1}
            />
          ))}

          {selectionBand ? (
            <rect
              x={selectionBand.x}
              y={0}
              width={selectionBand.width}
              height={plotHeight}
              className="timeline__band"
            />
          ) : null}

          {buckets.map((bucket, position) => {
            const total = bucket.events.length
            if (!total) return null
            const barHeight = Math.max(2, (total / peak) * (plotHeight - 8))
            const marked = highlighted
              ? bucket.events.filter((event) => highlighted.has(event.relationship.relationship_id))
                  .length
              : 0
            const markedHeight = marked ? Math.max(2, (marked / peak) * (plotHeight - 8)) : 0
            return (
              <g key={position}>
                <rect
                  x={toX(position) + bandOffset}
                  y={plotHeight - barHeight}
                  width={bandWidth}
                  height={barHeight}
                  rx={1.5}
                  className={`timeline__bar${hoverBucket === position ? ' is-hover' : ''}`}
                />
                {markedHeight ? (
                  <rect
                    x={toX(position) + bandOffset}
                    y={plotHeight - markedHeight}
                    width={bandWidth}
                    height={markedHeight}
                    rx={1.5}
                    className="timeline__bar timeline__bar--marked"
                  />
                ) : null}
              </g>
            )
          })}
        </svg>

        {hovered && hovered.events.length ? (
          <div
            className="timeline__tip"
            style={{
              left: Math.min(width - 150, Math.max(0, toX(hoverBucket) - 8)),
            }}
          >
            <strong>{formatDate(hovered.start)}</strong>
            <span>{plural(hovered.events.length, 'relationship')}</span>
          </div>
        ) : null}
      </div>

      {showAxisLabels ? (
        <div className="timeline__axis">
          <span className="mono">{formatDate(extent[0])}</span>
          <span className="timeline__axisnote">
            {plural(index.events.length, 'dated relationship')} · one bar per {unit}
            {index.untimedCount
              ? ` · ${index.untimedCount} undated, not plotted`
              : ''}
          </span>
          <span className="mono">{formatDate(extent[1])}</span>
        </div>
      ) : null}
    </div>
  )
}

/** The list of events inside the current window, used by the timeline page. */
export function EventList({ index, timeRange, onSelectRelationship, selection, limit }) {
  const events = useMemo(() => {
    const inWindow = timeRange
      ? index.events.filter((event) => event.at >= timeRange[0] && event.at <= timeRange[1])
      : index.events
    return limit ? inWindow.slice(0, limit) : inWindow
  }, [index.events, timeRange, limit])

  if (!events.length) {
    return (
      <EmptyState
        icon="clock"
        title="No activity in this window"
        detail="Narrow or clear the selected time range to see recorded relationships."
      />
    )
  }

  return (
    <ol className="eventlist">
      {events.map(({ at, relationship }) => {
        const classified = index.contextByRelationship.get(relationship.relationship_id)
        const context = classified?.context ?? 'unknown'
        const active = selection?.kind === 'relationship' && selection.id === relationship.relationship_id
        return (
          <li key={relationship.relationship_id}>
            <button
              type="button"
              className={`eventrow${active ? ' is-active' : ''}`}
              onClick={() => onSelectRelationship(relationship.relationship_id)}
            >
              <span className="eventrow__when mono">{formatDayMonth(at)}</span>
              <span
                className="eventrow__rail"
                style={{ background: contextMeta(context).color }}
                aria-hidden="true"
              />
              <span className="eventrow__body">
                <span className="eventrow__pair">
                  <span
                    style={{
                      color:
                        ENTITY_HEX[index.entityById.get(relationship.from_entity_id)?.entity_type] ??
                        'var(--text-muted)',
                    }}
                  >
                    ●
                  </span>
                  {index.labelOf(relationship.from_entity_id)}
                  <Icon name="arrowRight" size={11} />
                  <span
                    style={{
                      color:
                        ENTITY_HEX[index.entityById.get(relationship.to_entity_id)?.entity_type] ??
                        'var(--text-muted)',
                    }}
                  >
                    ●
                  </span>
                  {index.labelOf(relationship.to_entity_id)}
                </span>
                <span className="eventrow__meta">
                  {contextMeta(context).label}
                  {relationship.analyst_created ? ' · analyst created' : ''}
                  {' · '}
                  {relationship.evidence_count} evidence
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

export default Timeline
