/*
 * Named accessors for every backend route the workspace uses.
 *
 * Components never build a URL. If a route changes, or a query parameter gains
 * a constraint, it changes here once. Route names and parameters mirror
 * `backend/app/api/*.py` exactly; nothing in this file invents an endpoint.
 */

import { get, post, query } from './client.js'

const inv = (caseId) => `/api/investigations/${encodeURIComponent(caseId)}`
const an = (caseId) => `/api/analytics/${encodeURIComponent(caseId)}`

export const api = {
  health: () => get('/api/health'),

  /* ---- investigations (backend/app/api/investigations.py) ---- */
  investigations: () => get('/api/investigations'),
  investigation: (caseId) => get(inv(caseId)),
  entities: (caseId) => get(`${inv(caseId)}/entities`),
  relationships: (caseId) => get(`${inv(caseId)}/relationships`),
  evidence: (caseId) => get(`${inv(caseId)}/evidence`),
  documents: (caseId) => get(`${inv(caseId)}/documents`),
  runs: (caseId) => get(`${inv(caseId)}/runs`),
  graph: (caseId) => get(`${inv(caseId)}/graph`),
  createRelationship: (caseId, body) => post(`${inv(caseId)}/relationships`, body),

  /* ---- graph (backend/app/api/graph.py) ---- */
  elementEvidence: (graphId, elementId) =>
    get(`/api/graph/${encodeURIComponent(graphId)}/evidence/${encodeURIComponent(elementId)}`),

  /* ---- analytics, Stage C (backend/app/api/analytics.py) ---- */
  centrality: (caseId, metric = 'degree', limit) =>
    get(`${an(caseId)}/centrality${query({ metric, limit })}`),
  communities: (caseId) => get(`${an(caseId)}/communities`),
  bridges: (caseId) => get(`${an(caseId)}/bridges`),
  paths: (caseId, source, target, maxDepth = 3) =>
    get(`${an(caseId)}/paths${query({ source, target, max_depth: maxDepth })}`),
  temporal: (caseId, entityId) => get(`${an(caseId)}/temporal${query({ entity_id: entityId })}`),
  relationshipContext: (caseId) => get(`${an(caseId)}/relationship-context`),
  anomalies: (caseId, includeCrossCase = false) =>
    get(`${an(caseId)}/anomalies${query({ include_cross_case: includeCrossCase })}`),
  indicators: (caseId) => get(`${an(caseId)}/indicators`),
  leads: (caseId, includeCrossCase = false) =>
    get(`${an(caseId)}/leads${query({ include_cross_case: includeCrossCase })}`),
}
