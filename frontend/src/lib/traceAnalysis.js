/*
 * Trace Analysis.
 *
 * This is not a chat assistant and it does not generate prose. It assembles the
 * explanations Stage C already produced for the object in front of the
 * investigator, and shows where each one came from.
 *
 * Two rules hold everywhere in this file:
 *
 *   1. Every factor carries `source` - the endpoint whose output it is - and,
 *      where the backend supplied them, the evidence ids behind it. Nothing is
 *      asserted that cannot be followed back.
 *   2. Nothing is inferred about people. A factor describes a position in a
 *      graph or a pattern in time. It never characterises conduct, and the
 *      wording stays inside the vocabulary the backend itself uses:
 *      analytically notable, network priority, potential bridge, unusual
 *      pattern, cross-community connection.
 */

import {
  ANOMALY_TYPE_LABEL,
  CATEGORY_LABEL,
  INDICATOR_TYPE_LABEL,
  LEAD_TYPE_LABEL,
  contextMeta,
  relationshipLabel,
} from './domain.js'
import { formatDate, formatPercent, plural } from './format.js'

const factor = (partial) => ({ evidenceIds: [], relationshipIds: [], strength: null, ...partial })

/**
 * Why an entity is analytically notable in this case - or, honestly, why it is
 * not. An entity with no signals returns an empty factor list and a headline
 * that says so, rather than manufacturing significance.
 */
export function analyseEntity(entityId, index, intel) {
  const factors = []
  const label = index.labelOf(entityId)

  const degree = index.degreeByEntity.get(entityId)
  const betweenness = index.betweennessByEntity.get(entityId)
  const bridge = index.bridgeByEntity.get(entityId)
  const community = index.communityByEntity.get(entityId)
  const anomalies = index.anomaliesByEntity.get(entityId) ?? []
  const indicators = index.indicatorsByEntity.get(entityId) ?? []
  const leads = index.leadsByEntity.get(entityId) ?? []
  const temporal = index.temporalByEntity.get(entityId)

  if (degree) {
    factors.push(
      factor({
        kind: 'network',
        title: `Degree rank ${degree.rank} of ${intel?.centralityDegree?.count ?? '—'}`,
        detail: degree.explanation,
        source: 'analytics/centrality?metric=degree',
        strength: null,
        metric: `${degree.degree} direct relationship${degree.degree === 1 ? '' : 's'}`,
      }),
    )
  }

  if (betweenness && betweenness.value > 0) {
    factors.push(
      factor({
        kind: 'network',
        title: `Betweenness rank ${betweenness.rank}`,
        detail: betweenness.explanation,
        source: 'analytics/centrality?metric=betweenness',
        metric: betweenness.value.toFixed(2),
      }),
    )
  }

  if (bridge) {
    factors.push(
      factor({
        kind: 'network',
        title: `Potential bridge across ${bridge.community_count} clusters`,
        detail: bridge.explanation,
        source: 'analytics/bridges',
        evidenceIds: bridge.evidence_ids,
        relationshipIds: bridge.cross_community_relationship_ids,
        strength: bridge.normalized_betweenness,
        metric: formatPercent(bridge.confidence) + ' confidence',
      }),
    )
  }

  if (community) {
    factors.push(
      factor({
        kind: 'structure',
        title: `Member of ${community.community_id} (${plural(community.size, 'entity', 'entities')})`,
        detail: community.explanation,
        source: 'analytics/communities',
        relationshipIds: community.internal_relationship_ids,
        strength: community.internal_density,
        metric: `${formatPercent(community.internal_density)} internal density`,
      }),
    )
  }

  for (const signal of anomalies) {
    factors.push(
      factor({
        kind: 'anomaly',
        title: ANOMALY_TYPE_LABEL[signal.anomaly_type] ?? signal.anomaly_type,
        detail: signal.explanation,
        source: 'analytics/anomalies',
        evidenceIds: signal.evidence_ids,
        relationshipIds: signal.relationship_ids,
        strength: signal.signal_strength,
        category: signal.category,
        metric: `${CATEGORY_LABEL[signal.category] ?? signal.category} · ${formatPercent(signal.confidence)} confidence`,
      }),
    )
  }

  for (const indicator of indicators) {
    factors.push(
      factor({
        kind: 'indicator',
        title: INDICATOR_TYPE_LABEL[indicator.indicator_type] ?? indicator.indicator_type,
        detail: indicator.explanation,
        source: 'analytics/indicators',
        evidenceIds: indicator.evidence_ids,
        relationshipIds: indicator.relationship_ids,
        strength: indicator.confidence,
        metric: `${formatPercent(indicator.confidence)} confidence`,
      }),
    )
  }

  if (temporal && !temporal.insufficient_data) {
    factors.push(
      factor({
        kind: 'temporal',
        title: `Activity across ${plural(temporal.active_period_count, 'active day')}`,
        detail: temporal.explanation,
        source: 'analytics/temporal',
        strength: null,
        metric: `${formatDate(temporal.first_event_at)} → ${formatDate(temporal.last_event_at)}`,
      }),
    )
  }

  const priority = leads.length
    ? leads.reduce(
        (highest, lead) =>
          ({ high: 3, medium: 2, low: 1 })[lead.network_priority] >
          ({ high: 3, medium: 2, low: 1 })[highest]
            ? lead.network_priority
            : highest,
        'low',
      )
    : null

  const headline = factors.length
    ? `${label} is analytically notable in this case on ${plural(factors.length, 'ground')}.`
    : `Stage C found no distinguishing signal for ${label} in this case.`

  return {
    subject: label,
    headline,
    factors,
    leads,
    priority,
    empty: factors.length === 0,
    caveat:
      'Composed from this investigation’s Stage C outputs. Each factor names the analysis it came from. A structural position is not conduct, and none of this is evidence of wrongdoing.',
  }
}

/** What a relationship represents, and what the case holds in support of it. */
export function analyseRelationship(relationshipId, index) {
  const relationship = index.relationshipById.get(relationshipId)
  if (!relationship) return null
  const classified = index.contextByRelationship.get(relationshipId)
  const fromLabel = index.labelOf(relationship.from_entity_id)
  const toLabel = index.labelOf(relationship.to_entity_id)

  const factors = []

  if (classified) {
    factors.push(
      factor({
        kind: 'structure',
        title: `${contextMeta(classified.context).label} context`,
        detail: classified.analytical_note,
        source: 'analytics/relationship-context',
        evidenceIds: classified.evidence_ids,
        metric:
          classified.context_assertion === 'observed'
            ? 'context stated by the source'
            : 'context derived from the relationship type',
      }),
    )
    if (classified.interaction_count > 1) {
      factors.push(
        factor({
          kind: 'structure',
          title: `${classified.interaction_count} recorded interactions`,
          detail:
            'More than one source record asserts this same link. Stage A pooled them onto a single edge, so the evidence below is the union of every contributing record.',
          source: 'investigations/relationships',
          metric: `${relationship.evidence_count} evidence items`,
        }),
      )
    }
  }

  if (relationship.analyst_created) {
    factors.push(
      factor({
        kind: 'analyst',
        title: 'Asserted by an analyst',
        detail:
          'A human analyst recorded this link. No source document states it, so its provenance points at the assertion itself rather than at a document, and it is held as inferred.',
        source: 'investigations/relationships (analyst assertion)',
      }),
    )
  }

  const sharedIndicators = (index.indicatorsByEntity.get(relationship.from_entity_id) ?? []).filter(
    (indicator) => indicator.relationship_ids?.includes(relationshipId),
  )
  for (const indicator of sharedIndicators) {
    factors.push(
      factor({
        kind: 'indicator',
        title: INDICATOR_TYPE_LABEL[indicator.indicator_type] ?? indicator.indicator_type,
        detail: indicator.explanation,
        source: 'analytics/indicators',
        evidenceIds: indicator.evidence_ids,
        strength: indicator.confidence,
      }),
    )
  }

  return {
    subject: `${fromLabel} → ${toLabel}`,
    headline: `${relationshipLabel(relationship.relationship_type)}: ${fromLabel} and ${toLabel}.`,
    factors,
    empty: factors.length === 0,
    caveat:
      'A relationship is a link asserted by a record. Its context describes the setting it was recorded in, not a judgement about the parties.',
  }
}

/** Why a traced route is worth reading, stated only in terms of its own hops. */
export function analysePath(path, index) {
  if (!path) return null
  const contexts = new Map()
  let weakest = 'observed'
  const rank = { observed: 2, inferred: 1, unknown: 0 }
  for (const hop of path.edges) {
    contexts.set(hop.context, (contexts.get(hop.context) ?? 0) + 1)
    if (rank[hop.assertion_type] < rank[weakest]) weakest = hop.assertion_type
  }

  const factors = [
    factor({
      kind: 'structure',
      title: `${path.length}-hop route`,
      detail: path.explanation,
      source: 'analytics/paths',
      evidenceIds: path.evidence_ids,
      metric: `${formatPercent(path.path_confidence)} path confidence`,
    }),
    factor({
      kind: 'structure',
      title: 'Contexts crossed',
      detail: `This route passes through ${[...contexts.entries()]
        .map(([context, count]) => `${count} ${contextMeta(context).label.toLowerCase()}`)
        .join(', ')} relationship${path.edges.length === 1 ? '' : 's'}.`,
      source: 'analytics/relationship-context',
    }),
    factor({
      kind: weakest === 'observed' ? 'structure' : 'anomaly',
      title: `Held as ${weakest}`,
      detail:
        weakest === 'observed'
          ? 'Every hop on this route is stated directly by a source record.'
          : 'At least one hop was derived rather than stated, so the route as a whole is only as strong as that hop.',
      source: 'analytics/paths',
    }),
  ]

  const communities = new Set()
  for (const hop of path.edges) {
    const from = index.communityByEntity.get(hop.from_entity_id)
    const to = index.communityByEntity.get(hop.to_entity_id)
    if (from) communities.add(from.community_id)
    if (to) communities.add(to.community_id)
  }
  if (communities.size > 1) {
    factors.push(
      factor({
        kind: 'network',
        title: `Crosses ${communities.size} clusters`,
        detail: `The route leaves and re-enters clustered groups (${[...communities].join(', ')}). Cross-community routes are the ones a bridge entity sits on.`,
        source: 'analytics/communities',
      }),
    )
  }

  return {
    subject: `${path.edges[0].from_label} → ${path.edges[path.edges.length - 1].to_label}`,
    headline: `A ${path.length}-hop connection exists between these entities in the recorded data.`,
    factors,
    empty: false,
    caveat:
      'A path is a route through recorded relationships. Connection is not association, and a path is not proof of anything about the entities on it.',
  }
}

/** What a time window contains, computed from the relationships inside it. */
export function analyseWindow(range, index) {
  if (!range) return null
  const [from, to] = range
  const inWindow = index.events.filter((event) => event.at >= from && event.at <= to)
  if (!inWindow.length) {
    return {
      subject: `${formatDate(from)} – ${formatDate(to)}`,
      headline: 'No recorded relationship activity falls inside this window.',
      factors: [],
      empty: true,
      caveat: 'Absence of activity in a window means the case holds no timestamped record there.',
    }
  }

  const byType = new Map()
  const participants = new Set()
  for (const { relationship } of inWindow) {
    byType.set(relationship.relationship_type, (byType.get(relationship.relationship_type) ?? 0) + 1)
    participants.add(relationship.from_entity_id)
    participants.add(relationship.to_entity_id)
  }

  const ranked = [...byType.entries()].sort((a, b) => b[1] - a[1])
  const busiest = [...participants]
    .map((entityId) => ({
      entityId,
      label: index.labelOf(entityId),
      count: inWindow.filter(
        ({ relationship }) =>
          relationship.from_entity_id === entityId || relationship.to_entity_id === entityId,
      ).length,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 4)

  const factors = [
    factor({
      kind: 'temporal',
      title: `${plural(inWindow.length, 'relationship')} recorded`,
      detail: `Between ${formatDate(from)} and ${formatDate(to)}, ${plural(
        inWindow.length,
        'relationship',
      )} carry a timestamp inside this window, involving ${plural(
        participants.size,
        'entity',
        'entities',
      )}.`,
      source: 'investigations/relationships',
      relationshipIds: inWindow.map(({ relationship }) => relationship.relationship_id),
    }),
    factor({
      kind: 'temporal',
      title: 'Kinds of activity',
      detail: ranked
        .map(([type, count]) => `${count} × ${relationshipLabel(type).toLowerCase()}`)
        .join(', '),
      source: 'investigations/relationships',
    }),
  ]

  const overlapping = []
  for (const [entityId, signals] of index.anomaliesByEntity.entries()) {
    for (const signal of signals) {
      if (!signal.observed_from || !signal.observed_to) continue
      const start = new Date(signal.observed_from).getTime()
      if (start >= from.getTime() && start <= to.getTime()) {
        overlapping.push({ entityId, signal })
      }
    }
  }
  for (const { signal } of overlapping) {
    factors.push(
      factor({
        kind: 'anomaly',
        title: ANOMALY_TYPE_LABEL[signal.anomaly_type] ?? signal.anomaly_type,
        detail: signal.explanation,
        source: 'analytics/anomalies',
        evidenceIds: signal.evidence_ids,
        strength: signal.signal_strength,
      }),
    )
  }

  return {
    subject: `${formatDate(from)} – ${formatDate(to)}`,
    headline: `${plural(inWindow.length, 'relationship')} recorded in this window.`,
    factors,
    busiest,
    empty: false,
    caveat:
      'A busier window means more records carry timestamps there. Recording density is a property of the sources, not of the people in them.',
  }
}

export const LEAD_TYPE_TEXT = LEAD_TYPE_LABEL
