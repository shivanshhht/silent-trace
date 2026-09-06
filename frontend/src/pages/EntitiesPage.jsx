/*
 * The entity register.
 *
 * A dense, sortable table beside the same inspector the graph opens, so an
 * investigator can work from a list or from the map without changing tools.
 */

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../components/shell/AppShell.jsx'
import Icon, { entityIcon } from '../components/common/Icon.jsx'
import { ConfidenceCell, EntityIdentity } from '../components/common/Bits.jsx'
import { DataBoundary, EmptyState } from '../components/common/States.jsx'
import ContextDrawer from '../components/panels/ContextDrawer.jsx'
import CreateConnectionDialog from '../components/panels/CreateConnectionDialog.jsx'
import { useInvestigation } from '../state/InvestigationContext.jsx'
import { ENTITY_HEX, ENTITY_TYPES, entityLabel, entityMeta, priorityMeta } from '../lib/domain.js'
import { formatPercent } from '../lib/format.js'

const SORTS = {
  connections: (a, b) => b.connections - a.connections,
  name: (a, b) => a.label.localeCompare(b.label),
  type: (a, b) => a.entity.entity_type.localeCompare(b.entity.entity_type) || b.connections - a.connections,
  evidence: (a, b) => b.entity.evidence_count - a.entity.evidence_count,
}

export function EntitiesPage() {
  const {
    core,
    intel,
    index,
    selection,
    select,
    selectEntity,
    clearSelection,
    createRelationship,
    setTrace,
    reload,
  } = useInvestigation()
  const navigate = useNavigate()
  const [term, setTerm] = useState('')
  const [typeFilter, setTypeFilter] = useState(null)
  const [sort, setSort] = useState('connections')
  const [connectFrom, setConnectFrom] = useState(undefined)

  const rows = useMemo(() => {
    const needle = term.trim().toLowerCase()
    return index.entities
      .map((entity) => ({
        entity,
        label: entityLabel(entity),
        connections: (index.edgesByEntity.get(entity.canonical_id) ?? []).length,
        degree: index.degreeByEntity.get(entity.canonical_id),
        community: index.communityByEntity.get(entity.canonical_id),
        leads: index.leadsByEntity.get(entity.canonical_id) ?? [],
      }))
      .filter((row) => !typeFilter || row.entity.entity_type === typeFilter)
      .filter((row) => !needle || row.label.toLowerCase().includes(needle))
      .sort(SORTS[sort])
  }, [index, sort, term, typeFilter])

  const typeCounts = useMemo(() => {
    const counts = {}
    for (const entity of index.entities) counts[entity.entity_type] = (counts[entity.entity_type] ?? 0) + 1
    return counts
  }, [index.entities])

  return (
    <>
      <PageHeader
        title="Entities"
        description="Every identity the resolver produced for this case, with the evidence and network position behind it."
        actions={
          <>
            <div className="gsearch">
              <Icon name="search" size={13} />
              <input
                className="input"
                type="search"
                placeholder="Search entities"
                value={term}
                onChange={(event) => setTerm(event.target.value)}
              />
            </div>
            <select
              className="select"
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              aria-label="Sort entities"
            >
              <option value="connections">Most connected</option>
              <option value="name">Name</option>
              <option value="type">Type</option>
              <option value="evidence">Most evidenced</option>
            </select>
          </>
        }
      />

      <div className="page splitpage">
        <div className="splitpage__main">
          <div className="typefilter">
            <button
              type="button"
              className={`togglechip${typeFilter === null ? ' is-on' : ''}`}
              onClick={() => setTypeFilter(null)}
            >
              All
              <span className="num">{index.counts.entities}</span>
            </button>
            {ENTITY_TYPES.filter((type) => typeCounts[type]).map((type) => (
              <button
                key={type}
                type="button"
                className={`togglechip${typeFilter === type ? ' is-on' : ''}`}
                onClick={() => setTypeFilter(typeFilter === type ? null : type)}
              >
                <span style={{ color: ENTITY_HEX[type], display: 'inline-flex' }}>
                  <Icon name={entityIcon(type)} size={11} strokeWidth={1.5} />
                </span>
                {entityMeta(type).plural}
                <span className="num">{typeCounts[type]}</span>
              </button>
            ))}
          </div>

          <DataBoundary
            status={core.status}
            error={core.error}
            isEmpty={rows.length === 0}
            onRetry={reload}
            empty={
              <EmptyState
                icon="entities"
                title={index.counts.entities ? 'No entity matches these filters' : 'No entities in this case'}
                detail={
                  index.counts.entities
                    ? 'Clear the search or type filter to see the full register.'
                    : 'Nothing has been ingested into this investigation yet.'
                }
              />
            }
          >
            <div className="tablewrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Entity</th>
                    <th className="dtable__num">Links</th>
                    <th>Cluster</th>
                    <th>Resolution</th>
                    <th className="dtable__num">Evidence</th>
                    <th>Priority</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const active =
                      selection.kind === 'entity' && selection.id === row.entity.canonical_id
                    const priority = row.leads.length
                      ? row.leads.reduce(
                          (best, lead) =>
                            priorityMeta(lead.network_priority).rank > priorityMeta(best).rank
                              ? lead.network_priority
                              : best,
                          'low',
                        )
                      : null
                    return (
                      <tr
                        key={row.entity.canonical_id}
                        className={active ? 'is-active' : undefined}
                        onClick={() => select('entity', row.entity.canonical_id, 'register')}
                        tabIndex={0}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') select('entity', row.entity.canonical_id, 'register')
                        }}
                      >
                        <td>
                          <EntityIdentity entity={row.entity} />
                        </td>
                        <td className="dtable__num num">{row.connections}</td>
                        <td>
                          {row.community ? (
                            <span className="mono" style={{ color: 'var(--text-secondary)' }}>
                              {row.community.community_id}
                            </span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>—</span>
                          )}
                        </td>
                        <td>
                          <span className="restatus">
                            <span
                              className={`pill pill--square ${
                                row.entity.match_status === 'candidate_review'
                                  ? 'pill--medium'
                                  : 'pill--observed'
                              }`}
                            >
                              {row.entity.match_status.replace(/_/g, ' ')}
                            </span>
                            <span className="num restatus__conf">
                              {formatPercent(row.entity.match_confidence)}
                            </span>
                          </span>
                        </td>
                        <td className="dtable__num num">{row.entity.evidence_count}</td>
                        <td>
                          {priority ? (
                            <span className={`pill ${priorityMeta(priority).pill}`}>
                              {priorityMeta(priority).label}
                            </span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>—</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </DataBoundary>
        </div>

        {selection.kind ? (
          <div className="splitpage__side">
            <ContextDrawer
              inline
              selection={selection}
              index={index}
              intel={intel.data}
              onClose={clearSelection}
              onSelectEntity={(id) => select('entity', id, 'panel')}
              onSelectRelationship={(id) => select('relationship', id, 'panel')}
              onOpenEvidence={(id) => select('evidence', id, 'panel')}
              onTraceFrom={(entityId) => {
                setTrace({ active: true, source: entityId, target: null, maxDepth: 3 })
                selectEntity(entityId, 'register')
                navigate('/network')
              }}
              onCreateConnection={(entityId) => setConnectFrom(entityId)}
            />
          </div>
        ) : null}
      </div>

      {connectFrom !== undefined ? (
        <CreateConnectionDialog
          index={index}
          initialSource={connectFrom}
          onClose={() => setConnectFrom(undefined)}
          onCreate={async (body) => {
            const created = await createRelationship(body)
            select('relationship', created.relationship_id, 'analyst')
          }}
        />
      ) : null}
    </>
  )
}

export default EntitiesPage
