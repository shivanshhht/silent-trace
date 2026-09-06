/*
 * Loading, empty and error, defined once.
 *
 * Every data surface in the product renders through these, so a slow request
 * never shows a blank rectangle and a failed one never shows a plausible-looking
 * zero. Nothing here fabricates placeholder content: a skeleton is visibly a
 * skeleton, and an error repeats what the backend actually said.
 */

import Icon from './Icon.jsx'
import './states.css'

export function Skeleton({ rows = 3, height = 34 }) {
  return (
    <div className="skeleton" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton__row" style={{ height }} />
      ))}
    </div>
  )
}

export function EmptyState({ title, detail, icon = 'info', action }) {
  return (
    <div className="state state--empty">
      <Icon name={icon} size={18} />
      <p className="state__title">{title}</p>
      {detail ? <p className="state__detail">{detail}</p> : null}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry, compact = false }) {
  const message = error?.message ?? 'Something went wrong.'
  return (
    <div className={`state state--error${compact ? ' state--compact' : ''}`}>
      <Icon name="alert" size={18} />
      <p className="state__title">Could not load this data</p>
      <p className="state__detail">{message}</p>
      {onRetry ? (
        <button type="button" className="btn btn--sm" onClick={onRetry}>
          <Icon name="refresh" size={12} />
          Retry
        </button>
      ) : null}
    </div>
  )
}

/**
 * Render children only once data has genuinely arrived.
 *
 * `isEmpty` is asked separately from `status` because "loaded, and there is
 * nothing" and "not loaded yet" are different answers an investigator must be
 * able to tell apart.
 */
export function DataBoundary({
  status,
  error,
  isEmpty,
  empty,
  onRetry,
  skeleton,
  children,
}) {
  if (status === 'error') return <ErrorState error={error} onRetry={onRetry} />
  if (status === 'idle' || status === 'loading') return skeleton ?? <Skeleton />
  if (isEmpty) return empty ?? <EmptyState title="Nothing recorded here yet" />
  return children
}
