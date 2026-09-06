/*
 * Evidence, organised by the document it came from.
 *
 * A flat list of provenance rows would tell an investigator nothing about where
 * anything came from. Grouping by source keeps the chain visible - document,
 * then the rows quoted from it, then the graph objects those rows support - and
 * the inspector completes the return trip back to the graph.
 */

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../components/shell/AppShell.jsx'
import Icon from '../components/common/Icon.jsx'
import { PanelSection } from '../components/common/Bits.jsx'
import { DataBoundary, EmptyState } from '../components/common/States.jsx'
import { EvidenceRow } from '../components/panels/EvidenceList.jsx'
import ContextDrawer from '../components/panels/ContextDrawer.jsx'
import { useInvestigation } from '../state/InvestigationContext.jsx'
import { formatDate, plural } from '../lib/format.js'
import { hasSpan } from '../lib/evidence.js'

export function EvidencePage() {
  const { core, intel, index, selection, select, selectEntity, clearSelection, reload } =
    useInvestigation()
  const navigate = useNavigate()
  const [term, setTerm] = useState('')
  const [onlySpans, setOnlySpans] = useState(false)

  const evidence = core.data?.evidence?.evidence ?? []
  const documents = core.data?.documents?.documents ?? []

  const groups = useMemo(() => {
    const needle = term.trim().toLowerCase()
    const filtered = evidence
      .filter((row) => !onlySpans || hasSpan(row))
      .filter((row) => {
        if (!needle) return true
        const document = index.documentById.get(row.document_id)
        return (
          row.record_id.toLowerCase().includes(needle) ||
          row.snippet?.toLowerCase().includes(needle) ||
          document?.title?.toLowerCase().includes(needle) ||
          document?.content?.toLowerCase().includes(needle)
        )
      })

    const byDocument = new Map()
    for (const row of filtered) {
      const key = row.document_id ?? '__none__'
      if (!byDocument.has(key)) byDocument.set(key, [])
      byDocument.get(key).push(row)
    }

    return [...byDocument.entries()]
      .map(([documentId, rows]) => ({
        documentId,
        document: index.documentById.get(documentId),
        rows,
        spans: rows.filter(hasSpan).length,
      }))
      .sort((a, b) => b.rows.length - a.rows.length)
  }, [evidence, index, onlySpans, term])

  const totalSpans = evidence.filter(hasSpan).length

  return (
    <>
      <PageHeader
        title="Evidence"
        description="Every provenance row this case holds, grouped by the source it came from."
        actions={
          <>
            <button
              type="button"
              className={`btn${onlySpans ? ' is-active' : ''}`}
              onClick={() => setOnlySpans((value) => !value)}
              title="Show only rows that quote an exact character span"
            >
              <Icon name="document" size={13} />
              Quoted spans
              <span className="num">{totalSpans}</span>
            </button>
            <div className="gsearch">
              <Icon name="search" size={13} />
              <input
                className="input"
                type="search"
                placeholder="Search evidence"
                value={term}
                onChange={(event) => setTerm(event.target.value)}
              />
            </div>
          </>
        }
      />

      <div className="page splitpage">
        <div className="splitpage__main">
          <DataBoundary
            status={core.status}
            error={core.error}
            isEmpty={groups.length === 0}
            onRetry={reload}
            empty={
              <EmptyState
                icon="evidence"
                title={evidence.length ? 'No evidence matches' : 'No evidence recorded'}
                detail={
                  evidence.length
                    ? 'Clear the search or the span filter to see every row.'
                    : 'Nothing has been ingested into this investigation yet.'
                }
              />
            }
          >
            <div className="evgroups">
              {groups.map((group) => (
                <section key={group.documentId} className="card">
                  <header className="evdoc">
                    <span className="evdoc__icon">
                      <Icon name="document" size={15} strokeWidth={1.5} />
                    </span>
                    <div className="evdoc__text">
                      <h2 className="evdoc__title">
                        {group.document?.title ?? group.documentId.replace('__none__', 'Analyst assertions')}
                      </h2>
                      <p className="evdoc__meta">
                        {group.document ? (
                          <>
                            <span className="mono">{group.document.document_id}</span>
                            <span aria-hidden="true"> · </span>
                            {(group.document.source_type ?? '').replace(/_/g, ' ')}
                            {group.document.reliability ? (
                              <>
                                <span aria-hidden="true"> · </span>
                                {group.document.reliability} reliability
                              </>
                            ) : null}
                            <span aria-hidden="true"> · </span>
                            {formatDate(group.document.collected_at)}
                          </>
                        ) : (
                          'No stored document backs these rows.'
                        )}
                      </p>
                    </div>
                    <span className="evdoc__count">
                      {plural(group.rows.length, 'row')}
                      {group.spans ? ` · ${group.spans} quoted` : ''}
                    </span>
                  </header>

                  {group.document?.content ? (
                    <p className="evdoc__body">{group.document.content}</p>
                  ) : null}

                  <ul className="elist">
                    {group.rows.map((row) => (
                      <li key={row.provenance_id}>
                        <EvidenceRow
                          row={row}
                          index={index}
                          onOpen={(id) => select('evidence', id, 'evidence')}
                          active={selection.kind === 'evidence' && selection.id === row.provenance_id}
                          titleMode="record"
                          compact
                        />
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
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
              onSelectEntity={(id) => {
                selectEntity(id, 'evidence')
                navigate('/network')
              }}
              onSelectRelationship={(id) => select('relationship', id, 'evidence')}
              onOpenEvidence={(id) => select('evidence', id, 'evidence')}
              onTraceFrom={() => navigate('/network')}
              onCreateConnection={() => navigate('/network')}
            />
          </div>
        ) : (
          <div className="splitpage__side splitpage__side--hint">
            <PanelSection title="Evidence to graph">
              <p className="hinttext">
                Select any row to see the exact span it quotes inside its document, the extraction
                run that produced it, and the entities and relationships it supports. From there,
                one click puts you back on the graph at that object.
              </p>
              <p className="hinttext">
                {plural(documents.length, 'document')} · {plural(evidence.length, 'provenance row')} ·{' '}
                {plural(totalSpans, 'quoted span')}
              </p>
            </PanelSection>
          </div>
        )}
      </div>
    </>
  )
}

export default EvidencePage
