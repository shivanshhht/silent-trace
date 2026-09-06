/*
 * Small shared pieces of the investigation vocabulary.
 *
 * These exist so that an entity, an assertion state or a caveat is rendered
 * identically no matter which surface shows it. An entity looks the same in the
 * graph legend, an inspector, a lead and a path; that consistency is what makes
 * the colour taxonomy readable at all.
 */

import Icon, { entityIcon } from './Icon.jsx'
import { assertionMeta, contextMeta, entityLabel, entityMeta, entitySubtitle } from '../../lib/domain.js'
import { formatPercent } from '../../lib/format.js'
import './bits.css'

/** The type glyph in its type colour, on its soft ground. */
export function EntityGlyph({ type, size = 20 }) {
  const meta = entityMeta(type)
  return (
    <span
      className="eglyph"
      style={{ width: size, height: size, background: meta.soft, color: meta.color }}
      title={meta.label}
    >
      <Icon name={entityIcon(type)} size={Math.round(size * 0.62)} strokeWidth={1.5} />
    </span>
  )
}

/** A clickable entity reference. The single way an entity is named in prose. */
export function EntityChip({ entity, entityId, label, type, onSelect, active = false, size = 'md' }) {
  const resolvedType = type ?? entity?.entity_type
  const resolvedLabel = label ?? (entity ? entityLabel(entity) : entityId)
  const id = entityId ?? entity?.canonical_id
  const meta = entityMeta(resolvedType)
  return (
    <button
      type="button"
      className={`echip echip--${size}${active ? ' is-active' : ''}`}
      onClick={onSelect ? () => onSelect(id) : undefined}
      disabled={!onSelect}
      title={id}
    >
      <span className="echip__mark" style={{ color: meta.color }} aria-hidden="true">
        <Icon name={entityIcon(resolvedType)} size={size === 'sm' ? 11 : 12} strokeWidth={1.5} />
      </span>
      <span className="echip__label truncate">{resolvedLabel}</span>
    </button>
  )
}

/** Name plus qualifier plus glyph — the row form used in every entity list. */
export function EntityIdentity({ entity, size = 22 }) {
  const subtitle = entitySubtitle(entity)
  return (
    <span className="eident">
      <EntityGlyph type={entity?.entity_type} size={size} />
      <span className="eident__text">
        <span className="eident__name truncate">{entityLabel(entity)}</span>
        {subtitle ? <span className="eident__sub truncate">{subtitle}</span> : null}
      </span>
    </span>
  )
}

export function AssertionPill({ assertion, analystCreated = false, title }) {
  const meta = assertionMeta(assertion, analystCreated)
  return (
    <span className={`pill ${meta.pill}`} title={title ?? meta.description}>
      {meta.label}
    </span>
  )
}

export function ContextTag({ context }) {
  const meta = contextMeta(context)
  return (
    <span className="ctag" title={`Relationship context: ${meta.label}`}>
      <span className="ctag__dash" style={{ background: meta.color }} aria-hidden="true" />
      {meta.label}
    </span>
  )
}

export function Caveat({ children, icon = 'info' }) {
  if (!children) return null
  return (
    <p className="caveat">
      <Icon name={icon} size={13} />
      <span>{children}</span>
    </p>
  )
}

/** A short horizontal bar for a 0..1 value. Always shown beside its number. */
export function Meter({ value, color = 'var(--ink)', width = 44, title }) {
  const clamped = Math.max(0, Math.min(1, value ?? 0))
  return (
    <span className="meter" style={{ width }} title={title}>
      <span className="meter__fill" style={{ width: `${clamped * 100}%`, background: color }} />
    </span>
  )
}

export function ConfidenceCell({ value, color }) {
  return (
    <span className="confcell">
      <Meter value={value} color={color} />
      <span className="num confcell__value">{formatPercent(value)}</span>
    </span>
  )
}

/** A labelled metric in the dense analytical style used across inspectors. */
export function Stat({ label, value, hint, tone }) {
  return (
    <div className="stat" title={hint}>
      <span className="stat__label">{label}</span>
      <span className="stat__value num" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
    </div>
  )
}

export function PanelSection({ title, count, action, children, dense = false }) {
  return (
    <section className={`psection${dense ? ' psection--dense' : ''}`}>
      <header className="section-head">
        <h3 className="eyebrow">{title}</h3>
        {typeof count === 'number' ? <span className="count num">{count}</span> : null}
        {action}
      </header>
      {children}
    </section>
  )
}

/** The one place an identifier is rendered, so ids always look like ids. */
export function IdTag({ value, onClick, title }) {
  if (!value) return null
  const content = <span className="mono idtag__value">{value}</span>
  if (!onClick) {
    return (
      <span className="idtag" title={title ?? value}>
        {content}
      </span>
    )
  }
  return (
    <button type="button" className="idtag idtag--action" onClick={onClick} title={title ?? value}>
      {content}
    </button>
  )
}
