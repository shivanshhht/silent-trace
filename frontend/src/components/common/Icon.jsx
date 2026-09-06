/*
 * One icon family for the whole product.
 *
 * Every glyph is drawn on the same 16-unit grid with the same 1.4 stroke and
 * the same round joins, so nothing in the interface looks borrowed from a
 * different set. The six entity glyphs at the top form a deliberate taxonomy:
 * each is silhouette-distinct, so an entity type is readable from shape before
 * colour is read at all.
 */

const PATHS = {
  /* ---- entity taxonomy ---- */
  person: (
    <>
      <circle cx="8" cy="5.6" r="2.5" />
      <path d="M2.9 13.4c.5-2.6 2.6-4 5.1-4s4.6 1.4 5.1 4" />
    </>
  ),
  organization: (
    <>
      <path d="M2.6 13.6V4.2l5.1-1.8v11.2" />
      <path d="M7.7 6.5h5.7v7.1" />
      <path d="M1.5 13.6h13" />
      <path d="M4.6 6.4v.01M4.6 9.1v.01M10.4 9v.01M10.4 11.3v.01" />
    </>
  ),
  location: (
    <>
      <path d="M8 14.2s4.6-4.1 4.6-7.5a4.6 4.6 0 1 0-9.2 0c0 3.4 4.6 7.5 4.6 7.5Z" />
      <circle cx="8" cy="6.6" r="1.7" />
    </>
  ),
  phone: (
    <>
      <rect x="4.6" y="1.9" width="6.8" height="12.2" rx="1.6" />
      <path d="M6.9 4.1h2.2" />
      <circle cx="8" cy="11.7" r=".85" />
    </>
  ),
  vehicle: (
    <>
      <path d="M2 10.4V8.2l1.5-3.3a1.4 1.4 0 0 1 1.3-.8h6.4a1.4 1.4 0 0 1 1.3.8L14 8.2v2.2" />
      <path d="M2 10.4h12" />
      <path d="M3.3 8.1h9.4" />
      <circle cx="4.9" cy="11.9" r="1.3" />
      <circle cx="11.1" cy="11.9" r="1.3" />
    </>
  ),
  incident: (
    <>
      <path d="M8 1.9 14.1 8 8 14.1 1.9 8 8 1.9Z" />
      <path d="M8 5.4v3.1" />
      <path d="M8 10.9v.01" />
    </>
  ),
  entity: (
    <>
      <circle cx="8" cy="8" r="5.4" />
    </>
  ),

  /* ---- navigation ---- */
  overview: (
    <>
      <rect x="2.2" y="2.2" width="5" height="5" rx="1" />
      <rect x="8.8" y="2.2" width="5" height="5" rx="1" />
      <rect x="2.2" y="8.8" width="5" height="5" rx="1" />
      <rect x="8.8" y="8.8" width="5" height="5" rx="1" />
    </>
  ),
  network: (
    <>
      <circle cx="3.6" cy="4.2" r="1.8" />
      <circle cx="12.4" cy="6.1" r="1.8" />
      <circle cx="6.4" cy="12.4" r="1.8" />
      <path d="M5.3 5.4 10.7 5m-4.9 5.6 5.2-3M5 5.9l1 4.8" />
    </>
  ),
  entities: (
    <>
      <path d="M2.4 4.2h11.2M2.4 8h11.2M2.4 11.8h11.2" />
      <circle cx="2.4" cy="4.2" r=".1" />
    </>
  ),
  evidence: (
    <>
      <path d="M3.4 2.2h6l3.2 3.2v8.4H3.4z" />
      <path d="M9.3 2.2v3.4h3.3" />
      <path d="M5.6 9h4.8M5.6 11.4h3.2" />
    </>
  ),
  timeline: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.6V8l2.4 1.6" />
    </>
  ),
  analytics: (
    <>
      <path d="M2.4 13.6h11.2" />
      <path d="M4.4 13.6V9.2M7.5 13.6V5.4M10.6 13.6v-2.9M13 13.6V7.1" />
    </>
  ),
  leads: (
    <>
      <path d="M3.8 14V2.4h7.9l-1.8 3 1.8 3H3.8" />
    </>
  ),

  /* ---- actions and states ---- */
  trace: (
    <>
      <circle cx="3" cy="11.4" r="1.6" />
      <circle cx="13" cy="4.6" r="1.6" />
      <path d="M4.4 10.4c1.6-1.1 2-3.4 3.9-4.2 1.4-.6 2.5.2 3.4.8" />
      <path d="M9.6 6.5h2.1V4.4" />
    </>
  ),
  layout: (
    <>
      <circle cx="8" cy="3.4" r="1.5" />
      <circle cx="3.6" cy="11.8" r="1.5" />
      <circle cx="12.4" cy="11.8" r="1.5" />
      <path d="M7 4.7 4.6 10.4m4.4-5.7 2.4 5.7M5.1 11.8h5.8" />
    </>
  ),
  filter: (
    <>
      <path d="M2.4 3.4h11.2l-4.3 5v5l-2.6-1.6V8.4z" />
    </>
  ),
  fit: (
    <>
      <path d="M2.4 5.8V2.4h3.4M10.2 2.4h3.4v3.4M13.6 10.2v3.4h-3.4M5.8 13.6H2.4v-3.4" />
    </>
  ),
  zoomIn: (
    <>
      <circle cx="7.2" cy="7.2" r="4.6" />
      <path d="M10.6 10.6 14 14M5.4 7.2h3.6M7.2 5.4v3.6" />
    </>
  ),
  zoomOut: (
    <>
      <circle cx="7.2" cy="7.2" r="4.6" />
      <path d="M10.6 10.6 14 14M5.4 7.2h3.6" />
    </>
  ),
  search: (
    <>
      <circle cx="7.2" cy="7.2" r="4.6" />
      <path d="M10.6 10.6 14 14" />
    </>
  ),
  plus: <path d="M8 3.2v9.6M3.2 8h9.6" />,
  close: <path d="M4 4l8 8M12 4l-8 8" />,
  chevronRight: <path d="M6.2 3.6 10.6 8l-4.4 4.4" />,
  chevronDown: <path d="M3.6 6.2 8 10.6l4.4-4.4" />,
  chevronLeft: <path d="M9.8 3.6 5.4 8l4.4 4.4" />,
  arrowRight: <path d="M2.8 8h10.4M9.4 4.2 13.2 8l-3.8 3.8" />,
  link: (
    <>
      <path d="M6.6 9.4a2.6 2.6 0 0 0 3.9.3l2-2a2.6 2.6 0 0 0-3.7-3.7l-1.1 1.1" />
      <path d="M9.4 6.6a2.6 2.6 0 0 0-3.9-.3l-2 2a2.6 2.6 0 0 0 3.7 3.7l1.1-1.1" />
    </>
  ),
  info: (
    <>
      <circle cx="8" cy="8" r="6.1" />
      <path d="M8 7.3v4M8 5.1v.01" />
    </>
  ),
  alert: (
    <>
      <path d="M8 2.2 14.4 13H1.6L8 2.2Z" />
      <path d="M8 6.6v3M8 11.3v.01" />
    </>
  ),
  check: <path d="M3 8.4 6.4 11.8 13 5.2" />,
  refresh: (
    <>
      <path d="M13.4 8a5.4 5.4 0 1 1-1.6-3.8" />
      <path d="M13.6 2.2v3.2h-3.2" />
    </>
  ),
  document: (
    <>
      <path d="M3.4 2.2h6l3.2 3.2v8.4H3.4z" />
      <path d="M9.3 2.2v3.4h3.3" />
    </>
  ),
  target: (
    <>
      <circle cx="8" cy="8" r="5.6" />
      <circle cx="8" cy="8" r="2.1" />
    </>
  ),
  community: (
    <>
      <circle cx="5.2" cy="5.6" r="2.4" />
      <circle cx="11" cy="10.4" r="2.4" />
      <path d="M7.2 7.2l2.2 1.7" />
    </>
  ),
  clock: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.6V8l2.4 1.6" />
    </>
  ),
  dotGrid: (
    <>
      <path d="M4 4v.01M8 4v.01M12 4v.01M4 8v.01M8 8v.01M12 8v.01M4 12v.01M8 12v.01M12 12v.01" />
    </>
  ),
  spark: (
    <>
      <path d="M8 1.8 9.5 6l4.2 1.5L9.5 9 8 13.2 6.5 9 2.3 7.5 6.5 6 8 1.8Z" />
    </>
  ),
}

export function Icon({ name, size = 14, className, strokeWidth = 1.4, ...rest }) {
  const glyph = PATHS[name]
  if (!glyph) return null
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {glyph}
    </svg>
  )
}

export const ENTITY_ICON = {
  person: 'person',
  organization: 'organization',
  location: 'location',
  phone: 'phone',
  vehicle: 'vehicle',
  incident: 'incident',
}

export const entityIcon = (type) => ENTITY_ICON[type] ?? 'entity'

export default Icon
