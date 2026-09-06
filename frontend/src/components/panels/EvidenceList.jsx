/*
 * Evidence, rendered the same way everywhere it appears.
 *
 * An evidence row answers one question: why does Silent Trace believe this?
 * So it always shows the document it came from, how the reference was located,
 * and - when the extractor quoted a span - the quoted text with its character
 * range. A row without a span says so plainly instead of showing an empty quote.
 */

import Icon from '../common/Icon.jsx'
import { AssertionPill } from '../common/Bits.jsx'
import { EmptyState } from '../common/States.jsx'
import { formatDateTime, shortId } from '../../lib/format.js'
import { hasSpan } from '../../lib/evidence.js'

const PROVENANCE_NOTE = {
  observed: 'An exact source record or span backs this reference.',
  inferred: 'The link back to the source was derived rather than stated.',
  unknown: 'Supporting source evidence has not been established.',
}

/*
 * `titleMode` decides what the row leads with, because the useful fact differs
 * by context. Inside an inspector the reader knows the relationship and wants
 * the source, so the row leads with the document. Inside a list already grouped
 * under that document, repeating it says nothing - there the row leads with the
 * record it supports.
 */
export function EvidenceRow({
  row,
  index,
  onOpen,
  active = false,
  compact = false,
  titleMode = 'document',
}) {
  const document = index.documentById.get(row.document_id)
  const run = index.runById.get(row.extraction_run_id)
  const span = hasSpan(row)
  const recordTitle = `${(row.record_type ?? 'record').replace(/_/g, ' ')} · ${row.record_id}`
  const title =
    titleMode === 'record'
      ? recordTitle
      : (document?.title ?? row.document_id ?? 'Analyst assertion')

  return (
    <button
      type="button"
      className={`erow${active ? ' is-active' : ''}${compact ? ' erow--compact' : ''}`}
      onClick={onOpen ? () => onOpen(row.provenance_id) : undefined}
      disabled={!onOpen}
    >
      <span className="erow__head">
        <Icon name="document" size={13} />
        <span className="erow__title truncate">{title}</span>
        <AssertionPill assertion={row.assertion_type} />
      </span>

      {span ? (
        <span className="erow__quote">
          “{row.snippet}”
          <span className="mono erow__span">
            chars {row.character_start}–{row.character_end}
          </span>
        </span>
      ) : (
        <span className="erow__nospan">
          {row.source_type === 'analyst_assertion'
            ? 'Analyst assertion — no source document records this.'
            : 'Structured record — no character span applies.'}
        </span>
      )}

      <span className="erow__meta">
        <span className="mono">
          {titleMode === 'record'
            ? (document?.title ?? row.document_id ?? 'analyst assertion')
            : shortId(row.record_id, 16)}
        </span>
        <span className="erow__dot" aria-hidden="true">
          ·
        </span>
        <span title={PROVENANCE_NOTE[row.provenance_type]}>{row.provenance_type} provenance</span>
        {run ? (
          <>
            <span className="erow__dot" aria-hidden="true">
              ·
            </span>
            <span className="mono" title={`Extraction run ${run.run_id}`}>
              {run.kind} run
            </span>
          </>
        ) : null}
        <span className="erow__spacer" />
        <span>{formatDateTime(row.observed_at)}</span>
      </span>
    </button>
  )
}

export function EvidenceList({ rows, index, onOpen, activeId, emptyDetail }) {
  if (!rows.length) {
    return (
      <EmptyState
        icon="evidence"
        title="No evidence rows"
        detail={emptyDetail ?? 'Nothing in this case supports this element yet.'}
      />
    )
  }
  return (
    <ul className="elist">
      {rows.map((row) => (
        <li key={row.provenance_id}>
          <EvidenceRow
            row={row}
            index={index}
            onOpen={onOpen}
            active={activeId === row.provenance_id}
          />
        </li>
      ))}
    </ul>
  )
}
