/*
 * Recording an analyst's own assertion.
 *
 * The form deliberately offers no field for a document reference. The backend
 * refuses one, and offering it here would invite a fabricated citation. What
 * the analyst can supply is a reason, and that reason is stored as a note on the
 * assertion rather than dressed up as evidence.
 *
 * The result is written through the same pipeline as everything else and comes
 * back onto the graph immediately, carrying its own analyst-created marking.
 */

import { useEffect, useMemo, useState } from 'react'
import Icon from '../common/Icon.jsx'
import { EntityGlyph } from '../common/Bits.jsx'
import { CONTEXT_META, RELATIONSHIP_TYPES, entityLabel, entityMeta, relationshipLabel } from '../../lib/domain.js'

function EntityPicker({ label, value, onChange, entities, excludeId, autoFocus }) {
  const [term, setTerm] = useState('')
  const matches = useMemo(() => {
    const needle = term.trim().toLowerCase()
    return entities
      .filter((entity) => entity.canonical_id !== excludeId)
      .filter((entity) => !needle || entityLabel(entity).toLowerCase().includes(needle))
      .slice(0, 8)
  }, [entities, excludeId, term])

  const selected = entities.find((entity) => entity.canonical_id === value)

  return (
    <div className="field picker">
      <label>{label}</label>
      {selected ? (
        <div className="picker__chosen">
          <EntityGlyph type={selected.entity_type} size={22} />
          <span className="picker__name truncate">{entityLabel(selected)}</span>
          <span className="mono picker__id truncate">{selected.canonical_id}</span>
          <button
            type="button"
            className="btn btn--ghost btn--icon btn--sm"
            onClick={() => {
              onChange(null)
              setTerm('')
            }}
            aria-label={`Clear ${label}`}
          >
            <Icon name="close" size={11} />
          </button>
        </div>
      ) : (
        <>
          <input
            className="input"
            placeholder="Search entities in this case"
            value={term}
            autoFocus={autoFocus}
            onChange={(event) => setTerm(event.target.value)}
          />
          <ul className="picker__list">
            {matches.length === 0 ? (
              <li className="picker__none">No entity in this case matches.</li>
            ) : (
              matches.map((entity) => (
                <li key={entity.canonical_id}>
                  <button
                    type="button"
                    className="picker__option"
                    onClick={() => {
                      onChange(entity.canonical_id)
                      setTerm('')
                    }}
                  >
                    <EntityGlyph type={entity.entity_type} size={20} />
                    <span className="picker__name truncate">{entityLabel(entity)}</span>
                    <span className="picker__type">{entityMeta(entity.entity_type).label}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </>
      )}
    </div>
  )
}

export function CreateConnectionDialog({ index, initialSource, onClose, onCreate }) {
  const [from, setFrom] = useState(initialSource ?? null)
  const [to, setTo] = useState(null)
  const [type, setType] = useState('associated_with')
  const [context, setContext] = useState('')
  const [note, setNote] = useState('')
  const [analyst, setAnalyst] = useState('')
  const [occurredAt, setOccurredAt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape' && !submitting) onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, submitting])

  const valid = from && to && from !== to && type

  const submit = async (event) => {
    event.preventDefault()
    if (!valid || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await onCreate({
        from_entity_id: from,
        to_entity_id: to,
        relationship_type: type,
        confidence: 1.0,
        context: context || null,
        analyst_id: analyst.trim() || null,
        note: note.trim() || null,
        occurred_at: occurredAt ? new Date(occurredAt).toISOString() : null,
      })
      onClose()
    } catch (cause) {
      setError(cause)
      setSubmitting(false)
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Create an analyst connection">
      <div className="modal__scrim" onClick={submitting ? undefined : onClose} />
      <form className="modal__panel" onSubmit={submit}>
        <header className="modal__head">
          <div>
            <h2>Record a connection</h2>
            <p>
              This is your assertion, not a source’s. It enters the graph marked{' '}
              <strong>analyst created</strong> and is held as an inferred claim.
            </p>
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--icon"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
          >
            <Icon name="close" size={14} />
          </button>
        </header>

        <div className="modal__body">
          <div className="modal__pair">
            <EntityPicker
              label="From entity"
              value={from}
              onChange={setFrom}
              entities={index.entities}
              excludeId={to}
              autoFocus={!initialSource}
            />
            <EntityPicker
              label="To entity"
              value={to}
              onChange={setTo}
              entities={index.entities}
              excludeId={from}
              autoFocus={Boolean(initialSource)}
            />
          </div>

          <div className="modal__pair">
            <div className="field">
              <label htmlFor="rel-type">Relationship type</label>
              <select
                id="rel-type"
                className="select"
                value={type}
                onChange={(event) => setType(event.target.value)}
              >
                {RELATIONSHIP_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {relationshipLabel(value)}
                  </option>
                ))}
              </select>
              <p className="field__hint">
                Drawn from the canonical vocabulary. A new kind of link would be unanalysable.
              </p>
            </div>

            <div className="field">
              <label htmlFor="rel-context">Context (optional)</label>
              <select
                id="rel-context"
                className="select"
                value={context}
                onChange={(event) => setContext(event.target.value)}
              >
                <option value="">Not stated</option>
                {Object.entries(CONTEXT_META)
                  .filter(([key]) => key !== 'unknown')
                  .map(([key, meta]) => (
                    <option key={key} value={key}>
                      {meta.label}
                    </option>
                  ))}
              </select>
            </div>
          </div>

          <div className="modal__pair">
            <div className="field">
              <label htmlFor="rel-when">Occurred at (optional)</label>
              <input
                id="rel-when"
                className="input"
                type="datetime-local"
                value={occurredAt}
                onChange={(event) => setOccurredAt(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="rel-analyst">Analyst id (optional)</label>
              <input
                id="rel-analyst"
                className="input"
                value={analyst}
                placeholder="who is asserting this"
                onChange={(event) => setAnalyst(event.target.value)}
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="rel-note">Why you are asserting this (optional)</label>
            <textarea
              id="rel-note"
              className="textarea"
              value={note}
              placeholder="Your reasoning. Stored on the assertion, never presented as source evidence."
              onChange={(event) => setNote(event.target.value)}
              maxLength={1000}
            />
          </div>

          <p className="caveat">
            <Icon name="info" size={13} />
            <span>
              No document reference is accepted here, because no document records this. If a source
              already asserts the same link, Stage A pools both onto one edge and keeps the weaker
              claim — an analyst assertion can never promote a relationship to observed.
            </span>
          </p>

          {error ? (
            <p className="modal__error">
              <Icon name="alert" size={13} />
              {error.message}
            </p>
          ) : null}
        </div>

        <footer className="modal__foot">
          <button type="button" className="btn" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn--primary" disabled={!valid || submitting}>
            {submitting ? 'Recording…' : 'Record connection'}
          </button>
        </footer>
      </form>
    </div>
  )
}

export default CreateConnectionDialog
