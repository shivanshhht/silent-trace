/*
 * The vocabulary of the investigation, in one place.
 *
 * Every list here mirrors the backend's own Literal types
 * (`backend/app/schemas/investigation.py`). Colour, glyph and wording are
 * assigned once per term and used identically by the graph, the lists, the
 * inspectors and the analytics, so a colour always means the same thing.
 *
 * Colour never carries meaning alone: every coloured element in the product is
 * accompanied by its label, its glyph, or both.
 */

/* ---------------------------------------------------------------- entities */

export const ENTITY_TYPES = [
  'person',
  'organization',
  'location',
  'phone',
  'vehicle',
  'incident',
]

export const ENTITY_META = {
  person: { label: 'Person', plural: 'People', color: 'var(--e-person)', soft: 'var(--e-person-soft)' },
  organization: { label: 'Organization', plural: 'Organizations', color: 'var(--e-organization)', soft: 'var(--e-organization-soft)' },
  location: { label: 'Location', plural: 'Locations', color: 'var(--e-location)', soft: 'var(--e-location-soft)' },
  phone: { label: 'Phone', plural: 'Phones', color: 'var(--e-phone)', soft: 'var(--e-phone-soft)' },
  vehicle: { label: 'Vehicle', plural: 'Vehicles', color: 'var(--e-vehicle)', soft: 'var(--e-vehicle-soft)' },
  incident: { label: 'Incident', plural: 'Incidents', color: 'var(--e-incident)', soft: 'var(--e-incident-soft)' },
}

/** Literal hex values, for the graph renderer which cannot read CSS variables. */
export const ENTITY_HEX = {
  person: '#4a56c4',
  organization: '#2b7355',
  location: '#a8710d',
  phone: '#bf4a45',
  vehicle: '#3f6a71',
  incident: '#7d4fa8',
}

export const ENTITY_SOFT_HEX = {
  person: '#ecedfa',
  organization: '#e6f2ec',
  location: '#f8f0e0',
  phone: '#fbebea',
  vehicle: '#e8f1f2',
  incident: '#f2ecf8',
}

const FALLBACK_ENTITY = {
  label: 'Entity',
  plural: 'Entities',
  color: 'var(--text-muted)',
  soft: 'var(--surface-sunken)',
}

export const entityMeta = (type) => ENTITY_META[type] ?? { ...FALLBACK_ENTITY, label: type ?? 'Entity' }

/**
 * The human name of an entity, read from the attributes the source supplied.
 *
 * Each entity type stores its identifying value under a different key because
 * each canonical model names it differently. Nothing is invented: when an
 * attribute is absent the canonical value is shown instead, which is the
 * normalized form the resolver actually matched on.
 */
export function entityLabel(entity) {
  if (!entity) return ''
  const a = entity.attributes ?? {}
  switch (entity.entity_type) {
    case 'person':
      return a.display_name || entity.canonical_value
    case 'organization':
      return a.name || entity.canonical_value
    case 'location':
      return a.label || entity.canonical_value
    case 'phone':
      return a.number || entity.canonical_value
    case 'vehicle':
      return a.registration || entity.canonical_value
    case 'incident':
      return a.summary || entity.canonical_value
    default:
      return entity.canonical_value ?? entity.canonical_id ?? ''
  }
}

/** A short qualifier shown under the name. Null when the source states none. */
export function entitySubtitle(entity) {
  if (!entity) return null
  const a = entity.attributes ?? {}
  switch (entity.entity_type) {
    case 'person':
      return a.aliases?.length ? `aka ${a.aliases.join(', ')}` : null
    case 'organization':
      return a.organization_type || null
    case 'location':
      return a.locality || null
    case 'phone':
      return a.label || null
    case 'vehicle':
      return [a.make_model, a.color].filter(Boolean).join(' · ') || null
    case 'incident':
      return a.incident_type || null
    default:
      return null
  }
}

/* ----------------------------------------------------------- relationships */

export const RELATIONSHIP_TYPES = [
  'associated_with',
  'contacted',
  'met',
  'transacted_with',
  'located_at',
  'owns',
  'uses',
  'member_of',
  'involved_in',
]

export const RELATIONSHIP_LABEL = {
  associated_with: 'Associated with',
  contacted: 'Contacted',
  met: 'Met',
  transacted_with: 'Transacted with',
  located_at: 'Located at',
  owns: 'Owns',
  uses: 'Uses',
  member_of: 'Member of',
  involved_in: 'Involved in',
}

export const relationshipLabel = (type) =>
  RELATIONSHIP_LABEL[type] ?? String(type ?? '').replace(/_/g, ' ')

/* --------------------------------------------------------------- contexts */

export const CONTEXT_META = {
  communication: { label: 'Communication', color: 'var(--c-communication)', hex: '#4a56c4' },
  financial: { label: 'Financial', color: 'var(--c-financial)', hex: '#2b7355' },
  geographic: { label: 'Geographic', color: 'var(--c-geographic)', hex: '#a8710d' },
  family: { label: 'Family', color: 'var(--c-family)', hex: '#8a6a3f' },
  community: { label: 'Community', color: 'var(--c-community)', hex: '#5c6b5f' },
  business: { label: 'Business', color: 'var(--c-business)', hex: '#3f6a71' },
  operational: { label: 'Operational', color: 'var(--c-operational)', hex: '#7d4fa8' },
  unknown: { label: 'Unstated', color: 'var(--c-unknown)', hex: '#9aa09b' },
}

export const contextMeta = (context) => CONTEXT_META[context] ?? CONTEXT_META.unknown

/* ------------------------------------------------------------- assertions */

/*
 * How a claim is held, and who made it.
 *
 * `analyst` is not a backend assertion_type - it is the `analyst_created` flag
 * riding alongside one. It is surfaced as its own state because an analyst's
 * judgement must never be mistaken for something a document said or the
 * extractor read.
 */
export const ASSERTION_META = {
  observed: {
    label: 'Observed',
    description: 'Stated directly by a source record.',
    pill: 'pill--observed',
  },
  inferred: {
    label: 'Inferred',
    description: 'Produced by automated interpretation rather than stated by a source.',
    pill: 'pill--inferred',
  },
  unknown: {
    label: 'Unknown',
    description: 'The system could not establish how this claim is held.',
    pill: 'pill--inferred',
  },
  analyst: {
    label: 'Analyst created',
    description: 'Asserted by a human analyst. No source document records it.',
    pill: 'pill--analyst',
  },
}

export const assertionMeta = (assertion, analystCreated = false) =>
  analystCreated ? ASSERTION_META.analyst : ASSERTION_META[assertion] ?? ASSERTION_META.unknown

/* -------------------------------------------------------------- analytics */

export const PRIORITY_META = {
  high: { label: 'High', pill: 'pill--high', color: 'var(--priority-high)', rank: 3 },
  medium: { label: 'Medium', pill: 'pill--medium', color: 'var(--priority-medium)', rank: 2 },
  low: { label: 'Low', pill: 'pill--low', color: 'var(--priority-low)', rank: 1 },
}

export const priorityMeta = (priority) => PRIORITY_META[priority] ?? PRIORITY_META.low

export const LEAD_TYPE_LABEL = {
  potential_bridge_entity: 'Potential bridge entity',
  network_priority_entity: 'Network priority entity',
  coordinated_activity_pattern: 'Coordinated activity pattern',
  temporal_pattern_of_interest: 'Temporal pattern of interest',
}

export const ANOMALY_TYPE_LABEL = {
  temporal_burst: 'Temporal burst',
  temporal_gap: 'Temporal gap',
  network_bridge_load: 'Bridge load',
  network_degree_outlier: 'Degree outlier',
  financial_chain_participation: 'Financial chain participation',
  communication_overlap: 'Communication overlap',
  geographic_convergence: 'Geographic convergence',
  cross_case_recurrence: 'Cross-case recurrence',
}

export const INDICATOR_TYPE_LABEL = {
  repeated_co_occurrence: 'Repeated co-occurrence',
  hub_intermediary_structure: 'Hub and intermediary structure',
  financial_chain_structure: 'Financial chain structure',
  communication_overlap: 'Communication overlap',
  geographic_coordination: 'Geographic coordination',
  cross_case_recurrence: 'Cross-case recurrence',
}

export const CATEGORY_LABEL = {
  network: 'Network',
  temporal: 'Temporal',
  financial: 'Financial',
  communication: 'Communication',
  geographic: 'Geographic',
  structural: 'Structural',
  recurrence: 'Recurrence',
}

export const CENTRALITY_METRICS = [
  { value: 'degree', label: 'Degree', blurb: 'How many direct relationships an entity holds.' },
  { value: 'weighted_degree', label: 'Weighted degree', blurb: 'Direct relationships weighted by how well each is evidenced.' },
  { value: 'betweenness', label: 'Betweenness', blurb: 'How often an entity lies on the shortest route between two others.' },
  { value: 'closeness', label: 'Closeness', blurb: 'How short this entity’s routes to the rest of the network are.' },
]

export const CASE_STATUS_LABEL = {
  open: 'Open',
  active: 'Active',
  closed: 'Closed',
  archived: 'Archived',
}
