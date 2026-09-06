/*
 * One investigation, held once.
 *
 * Every surface in the product - graph, timeline, entity list, evidence,
 * analytics, leads - reads this context rather than fetching for itself. That
 * is what lets a selection made anywhere be reflected everywhere without any
 * page knowing about any other page.
 *
 * The case is loaded in two waves. `core` is the investigation itself: the
 * graph, its entities, relationships, evidence and documents. `intel` is the
 * Stage C analysis over it. They are separated because the graph must be
 * usable the moment it arrives, without waiting on betweenness to finish.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react'
import { api } from '../api/endpoints.js'
import { entityLabel } from '../lib/domain.js'
import { toDate } from '../lib/format.js'

const InvestigationContext = createContext(null)

const CASE_STORAGE_KEY = 'silent-trace.case'

const IDLE = { status: 'idle', data: null, error: null }
const loading = (previous) => ({ status: 'loading', data: previous?.data ?? null, error: null })
const ready = (data) => ({ status: 'ready', data, error: null })
const failed = (error) => ({ status: 'error', data: null, error })

/* ------------------------------------------------------------- selection */

const initialSelection = { kind: null, id: null, origin: null }

function selectionReducer(state, action) {
  switch (action.type) {
    case 'select':
      if (state.kind === action.kind && state.id === action.id) return state
      return { kind: action.kind, id: action.id, origin: action.origin ?? null }
    case 'clear':
      return initialSelection
    default:
      return state
  }
}

/* ---------------------------------------------------------------- filters */

const initialFilters = {
  entityTypes: [], // empty means every type
  contexts: [],
  assertion: 'all', // all | observed | inferred | analyst
  search: '',
}

/* ------------------------------------------------------------- provider */

export function InvestigationProvider({ children }) {
  const [cases, setCases] = useState(IDLE)
  const [caseTriage, setCaseTriage] = useState({})
  const [caseId, setCaseIdState] = useState(
    () => window.localStorage.getItem(CASE_STORAGE_KEY) ?? null,
  )
  const [core, setCore] = useState(IDLE)
  const [intel, setIntel] = useState(IDLE)
  const [selection, dispatchSelection] = useReducer(selectionReducer, initialSelection)
  const [filters, setFilters] = useState(initialFilters)
  const [timeRange, setTimeRange] = useState(null) // [Date, Date] or null for all time
  const [trace, setTrace] = useState({ active: false, source: null, target: null, maxDepth: 3 })
  const [pathResult, setPathResult] = useState(IDLE)
  const [activePathIndex, setActivePathIndex] = useState(0)
  const [focusToken, setFocusToken] = useState(0)
  const loadToken = useRef(0)

  /* ---- the list of investigations, and how each one is triaged ---- */
  const loadCases = useCallback(async () => {
    setCases(loading)
    try {
      const payload = await api.investigations()
      setCases(ready(payload))

      /* Lead priority per case, so the switcher can say which investigation
       * wants attention rather than only which is largest. A case whose leads
       * cannot be read is left out rather than shown as a confident zero. */
      const triage = {}
      await Promise.all(
        payload.investigations.map(async (item) => {
          try {
            const leads = await api.leads(item.case_id)
            const counts = { high: 0, medium: 0, low: 0, total: leads.count }
            for (const lead of leads.leads) counts[lead.network_priority] += 1
            triage[item.case_id] = counts
          } catch {
            /* an unreadable case simply has no triage entry */
          }
        }),
      )
      setCaseTriage(triage)
      return { payload, triage }
    } catch (error) {
      setCases(failed(error))
      return null
    }
  }, [])

  useEffect(() => {
    loadCases().then((result) => {
      if (!result?.payload?.investigations?.length) return
      const { payload, triage } = result
      if (payload.investigations.some((item) => item.case_id === caseId)) return

      /* Open the investigation that most wants attention: most high-priority
       * leads, then medium, then size. Nothing here names a case. */
      const ranked = [...payload.investigations].sort((a, b) => {
        const left = triage[a.case_id] ?? { high: 0, medium: 0 }
        const right = triage[b.case_id] ?? { high: 0, medium: 0 }
        return (
          right.high - left.high ||
          right.medium - left.medium ||
          b.relationship_count - a.relationship_count
        )
      })
      setCaseIdState(ranked[0].case_id)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setCaseId = useCallback((next) => {
    setCaseIdState(next)
    window.localStorage.setItem(CASE_STORAGE_KEY, next)
    dispatchSelection({ type: 'clear' })
    setTimeRange(null)
    setTrace({ active: false, source: null, target: null, maxDepth: 3 })
    setPathResult(IDLE)
    setFilters(initialFilters)
  }, [])

  /* ---- the case itself ---- */
  const loadCase = useCallback(async (id) => {
    if (!id) return
    const token = ++loadToken.current
    setCore(loading)
    setIntel(loading)

    try {
      const [summary, graph, entities, relationships, evidence, documents, runs] =
        await Promise.all([
          api.investigation(id),
          api.graph(id),
          api.entities(id),
          api.relationships(id),
          api.evidence(id),
          api.documents(id),
          api.runs(id),
        ])
      if (token !== loadToken.current) return
      setCore(ready({ summary, graph, entities, relationships, evidence, documents, runs }))
    } catch (error) {
      if (token !== loadToken.current) return
      setCore(failed(error))
      setIntel(failed(error))
      return
    }

    try {
      const [
        centralityDegree,
        centralityBetweenness,
        communities,
        bridges,
        anomalies,
        indicators,
        leads,
        relationshipContext,
        temporal,
      ] = await Promise.all([
        api.centrality(id, 'degree'),
        api.centrality(id, 'betweenness'),
        api.communities(id),
        api.bridges(id),
        api.anomalies(id),
        api.indicators(id),
        api.leads(id),
        api.relationshipContext(id),
        api.temporal(id),
      ])
      if (token !== loadToken.current) return
      setIntel(
        ready({
          centralityDegree,
          centralityBetweenness,
          communities,
          bridges,
          anomalies,
          indicators,
          leads,
          relationshipContext,
          temporal,
        }),
      )
    } catch (error) {
      if (token !== loadToken.current) return
      setIntel(failed(error))
    }
  }, [])

  useEffect(() => {
    if (caseId) {
      window.localStorage.setItem(CASE_STORAGE_KEY, caseId)
      loadCase(caseId)
    }
  }, [caseId, loadCase])

  const reload = useCallback(() => {
    loadCases()
    loadCase(caseId)
  }, [caseId, loadCase, loadCases])

  /* ---- indexes: built once per load, read by every surface ---- */
  const index = useMemo(() => buildIndex(core.data, intel.data), [core.data, intel.data])

  /* ---- selection helpers ---- */
  const select = useCallback((kind, id, origin) => {
    dispatchSelection({ type: 'select', kind, id, origin })
  }, [])
  const clearSelection = useCallback(() => dispatchSelection({ type: 'clear' }), [])

  /* Asking the graph to recentre. The counter is what the graph watches, so
   * re-selecting the same entity still re-focuses it. */
  const focusGraph = useCallback(() => setFocusToken((value) => value + 1), [])

  const selectEntity = useCallback(
    (entityId, origin) => {
      select('entity', entityId, origin)
      focusGraph()
    },
    [focusGraph, select],
  )

  /* ---- path tracing ---- */
  const runTrace = useCallback(
    async (source, target, maxDepth) => {
      if (!caseId || !source || !target) return
      setPathResult(loading)
      setActivePathIndex(0)
      try {
        const payload = await api.paths(caseId, source, target, maxDepth)
        setPathResult(ready(payload))
      } catch (error) {
        setPathResult(failed(error))
      }
    },
    [caseId],
  )

  /* Dropping the returned routes without dropping the endpoints: what happens
   * when the investigator starts a new trace from a fresh source. */
  const clearPaths = useCallback(() => {
    setPathResult(IDLE)
    setActivePathIndex(0)
  }, [])

  const clearTrace = useCallback(() => {
    setTrace((current) => ({ ...current, source: null, target: null }))
    clearPaths()
  }, [clearPaths])

  const activePath = useMemo(() => {
    const paths = pathResult.data?.paths ?? []
    return paths[activePathIndex] ?? null
  }, [pathResult.data, activePathIndex])

  /* ---- analyst relationship ---- */
  const createRelationship = useCallback(
    async (body) => {
      const created = await api.createRelationship(caseId, body)
      await loadCase(caseId)
      await loadCases()
      return created
    },
    [caseId, loadCase, loadCases],
  )

  const value = useMemo(
    () => ({
      cases,
      caseTriage,
      caseId,
      setCaseId,
      core,
      intel,
      index,
      reload,
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
      focusGraph,
      createRelationship,
    }),
    [
      cases,
      caseTriage,
      caseId,
      setCaseId,
      core,
      intel,
      index,
      reload,
      selection,
      select,
      selectEntity,
      clearSelection,
      filters,
      timeRange,
      trace,
      runTrace,
      clearTrace,
      clearPaths,
      pathResult,
      activePath,
      activePathIndex,
      focusToken,
      focusGraph,
      createRelationship,
    ],
  )

  return <InvestigationContext.Provider value={value}>{children}</InvestigationContext.Provider>
}

export function useInvestigation() {
  const context = useContext(InvestigationContext)
  if (!context) throw new Error('useInvestigation must be used inside InvestigationProvider')
  return context
}

/* --------------------------------------------------------------- indexing */

const emptyIndex = {
  entities: [],
  entityById: new Map(),
  relationships: [],
  relationshipById: new Map(),
  evidenceById: new Map(),
  evidenceByRecordId: new Map(),
  documentById: new Map(),
  runById: new Map(),
  nodeById: new Map(),
  edgeById: new Map(),
  neighbours: new Map(),
  edgesByEntity: new Map(),
  labelOf: () => '',
  contextByRelationship: new Map(),
  communityByEntity: new Map(),
  communityById: new Map(),
  degreeByEntity: new Map(),
  betweennessByEntity: new Map(),
  bridgeByEntity: new Map(),
  anomaliesByEntity: new Map(),
  indicatorsByEntity: new Map(),
  leadsByEntity: new Map(),
  temporalByEntity: new Map(),
  events: [],
  untimedCount: 0,
  timeExtent: null,
  counts: { entities: 0, relationships: 0, evidence: 0, documents: 0 },
}

function pushInto(map, key, item) {
  if (!key) return
  const bucket = map.get(key)
  if (bucket) bucket.push(item)
  else map.set(key, [item])
}

function buildIndex(coreData, intelData) {
  if (!coreData) return emptyIndex

  const entities = coreData.entities?.entities ?? []
  const relationships = coreData.relationships?.relationships ?? []
  const evidence = coreData.evidence?.evidence ?? []
  const documents = coreData.documents?.documents ?? []
  const runs = coreData.runs?.runs ?? []
  const nodes = coreData.graph?.nodes ?? []
  const edges = coreData.graph?.edges ?? []

  const entityById = new Map(entities.map((entity) => [entity.canonical_id, entity]))
  const relationshipById = new Map(
    relationships.map((relationship) => [relationship.relationship_id, relationship]),
  )
  const evidenceById = new Map(evidence.map((item) => [item.provenance_id, item]))
  const evidenceByRecordId = new Map()
  for (const item of evidence) pushInto(evidenceByRecordId, item.record_id, item)
  const documentById = new Map(documents.map((doc) => [doc.document_id, doc]))
  const runById = new Map(runs.map((run) => [run.run_id, run]))
  const nodeById = new Map(nodes.map((node) => [node.node_id, node]))
  const edgeById = new Map(edges.map((edge) => [edge.edge_id, edge]))

  const labelOf = (entityId) => {
    const entity = entityById.get(entityId)
    if (entity) return entityLabel(entity)
    const node = nodeById.get(entityId)
    return node ? entityLabel({ ...node, canonical_value: node.node_id }) : entityId
  }

  /* adjacency, derived from the relationships the case actually holds */
  const neighbours = new Map()
  const edgesByEntity = new Map()
  for (const relationship of relationships) {
    const { from_entity_id: from, to_entity_id: to } = relationship
    if (!neighbours.has(from)) neighbours.set(from, new Set())
    if (!neighbours.has(to)) neighbours.set(to, new Set())
    neighbours.get(from).add(to)
    neighbours.get(to).add(from)
    pushInto(edgesByEntity, from, relationship)
    pushInto(edgesByEntity, to, relationship)
  }

  /* The timeline plots `occurred_at` alone: when the relationship happened.
   * `observed_at` is when the record was collected, which is a different
   * quantity - an analyst assertion recorded today about a link from March
   * would otherwise drag the whole axis to today. A relationship without an
   * occurrence date is untimed rather than assigned a substitute one. */
  const events = relationships
    .map((relationship) => {
      const at = toDate(relationship.occurred_at)
      return at ? { at, relationship } : null
    })
    .filter(Boolean)
    .sort((a, b) => a.at - b.at)

  const untimedCount = relationships.length - events.length
  const timeExtent = events.length ? [events[0].at, events[events.length - 1].at] : null

  const base = {
    ...emptyIndex,
    entities,
    entityById,
    relationships,
    relationshipById,
    evidenceById,
    evidenceByRecordId,
    documentById,
    runById,
    nodeById,
    edgeById,
    neighbours,
    edgesByEntity,
    labelOf,
    events,
    untimedCount,
    timeExtent,
    counts: {
      entities: entities.length,
      relationships: relationships.length,
      evidence: evidence.length,
      documents: documents.length,
    },
  }

  if (!intelData) return base

  const contextByRelationship = new Map(
    (intelData.relationshipContext?.relationships ?? []).map((row) => [row.relationship_id, row]),
  )

  const communityById = new Map(
    (intelData.communities?.communities ?? []).map((community) => [
      community.community_id,
      community,
    ]),
  )
  const communityByEntity = new Map()
  for (const community of intelData.communities?.communities ?? []) {
    for (const member of community.member_entity_ids) communityByEntity.set(member, community)
  }

  const degreeByEntity = new Map(
    (intelData.centralityDegree?.scores ?? []).map((score) => [score.entity_id, score]),
  )
  const betweennessByEntity = new Map(
    (intelData.centralityBetweenness?.scores ?? []).map((score) => [score.entity_id, score]),
  )
  const bridgeByEntity = new Map(
    (intelData.bridges?.bridges ?? []).map((bridge) => [bridge.entity_id, bridge]),
  )

  const anomaliesByEntity = new Map()
  for (const signal of intelData.anomalies?.signals ?? []) {
    pushInto(anomaliesByEntity, signal.entity_id, signal)
  }

  const indicatorsByEntity = new Map()
  for (const indicator of intelData.indicators?.indicators ?? []) {
    for (const entityId of indicator.entity_ids) pushInto(indicatorsByEntity, entityId, indicator)
  }

  const leadsByEntity = new Map()
  for (const lead of intelData.leads?.leads ?? []) {
    for (const entityId of lead.subject_entity_ids) pushInto(leadsByEntity, entityId, lead)
  }

  const temporalByEntity = new Map(
    (intelData.temporal?.profiles ?? []).map((profile) => [profile.entity_id, profile]),
  )

  return {
    ...base,
    contextByRelationship,
    communityById,
    communityByEntity,
    degreeByEntity,
    betweennessByEntity,
    bridgeByEntity,
    anomaliesByEntity,
    indicatorsByEntity,
    leadsByEntity,
    temporalByEntity,
  }
}
