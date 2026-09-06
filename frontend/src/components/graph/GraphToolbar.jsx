/*
 * Graph controls. Every control here changes what is on the canvas; there is
 * nothing decorative and nothing that only looks like a feature.
 */

import { useEffect, useRef, useState } from 'react'
import Icon, { entityIcon } from '../common/Icon.jsx'
import { CONTEXT_META, ENTITY_HEX, ENTITY_TYPES, entityMeta } from '../../lib/domain.js'
import { LAYOUTS } from '../../lib/graphStyle.js'

function useDismiss(onDismiss) {
  const ref = useRef(null)
  useEffect(() => {
    const onPointer = (event) => {
      if (ref.current && !ref.current.contains(event.target)) onDismiss()
    }
    const onKey = (event) => {
      if (event.key === 'Escape') onDismiss()
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [onDismiss])
  return ref
}

function toggle(list, value) {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

function FilterPopover({ filters, setFilters, onClose, contextCounts }) {
  const ref = useDismiss(onClose)
  const active =
    filters.entityTypes.length + filters.contexts.length + (filters.assertion !== 'all' ? 1 : 0)

  return (
    <div className="popover popover--right" ref={ref} role="dialog" aria-label="Graph filters">
      <div className="popover__group">
        <p className="eyebrow popover__title">Entity type</p>
        <div className="popover__options">
          {ENTITY_TYPES.map((type) => {
            const on = filters.entityTypes.includes(type)
            return (
              <button
                key={type}
                type="button"
                className={`togglechip${on ? ' is-on' : ''}`}
                aria-pressed={on}
                onClick={() =>
                  setFilters((current) => ({
                    ...current,
                    entityTypes: toggle(current.entityTypes, type),
                  }))
                }
              >
                <span
                  className="togglechip__swatch"
                  style={{ background: ENTITY_HEX[type] }}
                  aria-hidden="true"
                />
                {entityMeta(type).label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="popover__group">
        <p className="eyebrow popover__title">Relationship context</p>
        <div className="popover__options">
          {Object.entries(CONTEXT_META)
            .filter(([key]) => (contextCounts ? (contextCounts[key] ?? 0) > 0 : true))
            .map(([key, meta]) => {
              const on = filters.contexts.includes(key)
              return (
                <button
                  key={key}
                  type="button"
                  className={`togglechip${on ? ' is-on' : ''}`}
                  aria-pressed={on}
                  onClick={() =>
                    setFilters((current) => ({
                      ...current,
                      contexts: toggle(current.contexts, key),
                    }))
                  }
                >
                  <span
                    className="togglechip__dash"
                    style={{ background: meta.hex }}
                    aria-hidden="true"
                  />
                  {meta.label}
                  {contextCounts ? (
                    <span className="num" style={{ color: 'var(--text-muted)' }}>
                      {contextCounts[key] ?? 0}
                    </span>
                  ) : null}
                </button>
              )
            })}
        </div>
      </div>

      <div className="popover__group">
        <p className="eyebrow popover__title">How the claim is held</p>
        <div className="popover__options">
          {[
            ['all', 'All'],
            ['observed', 'Observed'],
            ['inferred', 'Inferred'],
            ['analyst', 'Analyst created'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`togglechip${filters.assertion === value ? ' is-on' : ''}`}
              aria-pressed={filters.assertion === value}
              onClick={() => setFilters((current) => ({ ...current, assertion: value }))}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {active > 0 ? (
        <div className="popover__group">
          <button
            type="button"
            className="btn btn--sm"
            onClick={() =>
              setFilters((current) => ({
                ...current,
                entityTypes: [],
                contexts: [],
                assertion: 'all',
              }))
            }
          >
            Clear {active} filter{active === 1 ? '' : 's'}
          </button>
        </div>
      ) : null}
    </div>
  )
}

function LayoutPopover({ layoutName, setLayoutName, onClose }) {
  const ref = useDismiss(onClose)
  return (
    <div className="popover" ref={ref} role="dialog" aria-label="Graph layout">
      <p className="eyebrow popover__title">Arrangement</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {Object.entries(LAYOUTS).map(([key, config]) => (
          <button
            key={key}
            type="button"
            className={`layoutopt${layoutName === key ? ' is-on' : ''}`}
            onClick={() => {
              setLayoutName(key)
              onClose()
            }}
          >
            <span className="layoutopt__name">{config.label}</span>
            <span className="layoutopt__hint">{config.hint}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export function GraphToolbar({
  filters,
  setFilters,
  layoutName,
  setLayoutName,
  contextCounts,
  onFit,
  onZoom,
  trace,
  setTrace,
  onClearTrace,
  hasTrace,
  onCreateConnection,
}) {
  const [open, setOpen] = useState(null)
  const activeFilters =
    filters.entityTypes.length + filters.contexts.length + (filters.assertion !== 'all' ? 1 : 0)

  return (
    <div className="gtoolbar">
      <div className="gsearch">
        <Icon name="search" size={13} />
        <input
          className="input"
          type="search"
          placeholder="Find in graph"
          value={filters.search}
          onChange={(event) =>
            setFilters((current) => ({ ...current, search: event.target.value }))
          }
          aria-label="Find an entity in the graph"
        />
      </div>

      <div className="filter-wrap">
        <button
          type="button"
          className={`btn${activeFilters ? ' is-active' : ''}`}
          onClick={() => setOpen(open === 'filter' ? null : 'filter')}
          aria-expanded={open === 'filter'}
        >
          <Icon name="filter" size={13} />
          Filter
          {activeFilters ? <span className="num">{activeFilters}</span> : null}
        </button>
        {open === 'filter' ? (
          <FilterPopover
            filters={filters}
            setFilters={setFilters}
            contextCounts={contextCounts}
            onClose={() => setOpen(null)}
          />
        ) : null}
      </div>

      <div className="filter-wrap">
        <button
          type="button"
          className="btn"
          onClick={() => setOpen(open === 'layout' ? null : 'layout')}
          aria-expanded={open === 'layout'}
        >
          <Icon name="layout" size={13} />
          {LAYOUTS[layoutName]?.label ?? 'Layout'}
          <Icon name="chevronDown" size={11} />
        </button>
        {open === 'layout' ? (
          <LayoutPopover
            layoutName={layoutName}
            setLayoutName={setLayoutName}
            onClose={() => setOpen(null)}
          />
        ) : null}
      </div>

      <span className="gtoolbar__divider" aria-hidden="true" />

      <button
        type="button"
        className={`btn${trace.active ? ' is-active' : ''}`}
        onClick={() => {
          if (trace.active) {
            onClearTrace()
            setTrace((current) => ({ ...current, active: false }))
          } else {
            setTrace((current) => ({ ...current, active: true, source: null, target: null }))
          }
        }}
        title="Follow the recorded route between two entities"
      >
        <Icon name="trace" size={13} />
        Trace path
      </button>

      {hasTrace ? (
        <button type="button" className="btn btn--ghost btn--sm" onClick={onClearTrace}>
          Clear trace
        </button>
      ) : null}

      <span className="gtoolbar__spacer" />

      <button type="button" className="btn" onClick={onCreateConnection}>
        <Icon name="plus" size={13} />
        Connection
      </button>

      <span className="gtoolbar__divider" aria-hidden="true" />

      <div className="btn-group">
        <button type="button" className="btn btn--icon" onClick={() => onZoom(1 / 1.28)} title="Zoom out">
          <Icon name="zoomOut" size={13} />
        </button>
        <button type="button" className="btn btn--icon" onClick={() => onZoom(1.28)} title="Zoom in">
          <Icon name="zoomIn" size={13} />
        </button>
        <button type="button" className="btn btn--icon" onClick={onFit} title="Fit to view">
          <Icon name="fit" size={13} />
        </button>
      </div>
    </div>
  )
}

export function GraphLegend({ counts, collapsed, onToggle }) {
  if (collapsed) {
    return (
      <button type="button" className="btn btn--sm glegend glegend--mini" onClick={onToggle}>
        <Icon name="info" size={12} /> Legend
      </button>
    )
  }
  return (
    <div className="glegend">
      <button
        type="button"
        className="btn btn--ghost btn--icon btn--sm glegend__toggle"
        onClick={onToggle}
        aria-label="Hide legend"
      >
        <Icon name="close" size={11} />
      </button>
      <div>
        <p className="eyebrow" style={{ marginBottom: 5 }}>
          Entities
        </p>
        <div className="glegend__row">
          {ENTITY_TYPES.filter((type) => (counts?.[type] ?? 0) > 0).map((type) => (
            <span className="glegend__item" key={type}>
              <span style={{ color: ENTITY_HEX[type], display: 'inline-flex' }}>
                <Icon name={entityIcon(type)} size={12} strokeWidth={1.5} />
              </span>
              {entityMeta(type).label}
              <span className="num" style={{ color: 'var(--text-muted)' }}>
                {counts[type]}
              </span>
            </span>
          ))}
        </div>
      </div>
      <div>
        <p className="eyebrow" style={{ marginBottom: 5 }}>
          Relationship claim
        </p>
        <div className="glegend__row">
          <span className="glegend__item">
            <span className="glegend__line" style={{ borderTopStyle: 'solid' }} /> Observed
          </span>
          <span className="glegend__item">
            <span className="glegend__line" style={{ borderTopStyle: 'dashed' }} /> Inferred
          </span>
          <span className="glegend__item">
            <span
              className="glegend__line"
              style={{ borderTopStyle: 'dotted', borderTopColor: 'var(--analyst)', borderTopWidth: 2 }}
            />
            Analyst
          </span>
        </div>
      </div>
      <p style={{ fontSize: 10.5, color: 'var(--text-muted)', lineHeight: 1.45 }}>
        Edge colour is the context a relationship was recorded in. Line weight is how much
        evidence supports it.
      </p>
    </div>
  )
}
