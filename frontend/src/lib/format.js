/* Presentation helpers. Nothing here invents a value: an absent input yields a
 * visible em dash rather than a plausible-looking substitute. */

export const EMPTY = '—'

const DATE_TIME = new Intl.DateTimeFormat('en-GB', {
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const DATE_ONLY = new Intl.DateTimeFormat('en-GB', {
  year: 'numeric',
  month: 'short',
  day: '2-digit',
})

const DAY_MONTH = new Intl.DateTimeFormat('en-GB', { month: 'short', day: '2-digit' })

/** Timestamps arrive naive-UTC from SQLite; treat a bare stamp as UTC. */
export function toDate(value) {
  if (!value) return null
  const normalized =
    typeof value === 'string' && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? `${value}Z` : value
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

export const formatDateTime = (value) => {
  const date = toDate(value)
  return date ? DATE_TIME.format(date).replace(',', '') : EMPTY
}

export const formatDate = (value) => {
  const date = toDate(value)
  return date ? DATE_ONLY.format(date) : EMPTY
}

export const formatDayMonth = (value) => {
  const date = toDate(value)
  return date ? DAY_MONTH.format(date) : EMPTY
}

export const formatRange = (from, to) => {
  if (!from && !to) return EMPTY
  if (from && to) return `${formatDate(from)} – ${formatDate(to)}`
  return formatDate(from ?? to)
}

/** Confidence and strength are 0..1 fractions from the backend. */
export const formatPercent = (value, digits = 0) =>
  typeof value === 'number' ? `${(value * 100).toFixed(digits)}%` : EMPTY

export const formatNumber = (value, digits = 2) => {
  if (typeof value !== 'number') return EMPTY
  if (Number.isInteger(value)) return String(value)
  return value.toFixed(digits)
}

export const plural = (count, singular, pluralForm) =>
  `${count} ${count === 1 ? singular : pluralForm ?? `${singular}s`}`

/** Shorten a long identifier for a dense row while keeping both ends legible. */
export const shortId = (id, head = 10) => {
  if (!id) return EMPTY
  return id.length <= head + 4 ? id : `${id.slice(0, head)}…${id.slice(-3)}`
}

export const titleCase = (value) =>
  String(value ?? '')
    .replace(/_/g, ' ')
    .replace(/^\w/, (character) => character.toUpperCase())

/** Case ids read `case_coordinated-001`; the display form drops the prefix. */
export const caseShortName = (caseId) =>
  titleCase(String(caseId ?? '').replace(/^case_/, '').replace(/-/g, ' '))
