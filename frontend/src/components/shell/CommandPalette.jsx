/*
 * Ctrl+K: reach anything in the investigation without navigating to it.
 *
 * The palette searches what the case actually holds - its entities,
 * relationships, evidence, documents and leads - plus the handful of places a
 * page can be. Selecting a result does the same thing clicking it anywhere else
 * would: it sets the shared selection and puts the right page in front of you.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Icon, { entityIcon } from '../common/Icon.jsx'
import { useInvestigation } from '../../state/InvestigationContext.jsx'
import {
  ENTITY_HEX,
  LEAD_TYPE_LABEL,
  entityLabel,
  entityMeta,
  priorityMeta,
  relationshipLabel,
} from '../../lib/domain.js'
import { formatDate } from '../../lib/format.js'
import './palette.css'

const PAGES = [
  { id: 'page:/', label: 'Overview', to: '/', icon: 'overview' },
  { id: 'page:/network', label: 'Network', to: '/network', icon: 'network' },
  { id: 'page:/entities', label: 'Entities', to: '/entities', icon: 'entities' },
  { id: 'page:/evidence', label: 'Evidence', to: '/evidence', icon: 'evidence' },
  { id: 'page:/timeline', label: 'Timeline', to: '/timeline', icon: 'timeline' },
  { id: 'page:/analytics', label: 'Analytics', to: '/analytics', icon: 'analytics' },
  { id: 'page:/leads', label: 'Leads', to: '/leads', icon: 'leads' },
]

const LIMIT_PER_GROUP = 6

function buildResults(term, index, intel) {
  const needle = term.trim().toLowerCase()
  const match = (text) => !needle || String(text ?? '').toLowerCase().includes(needle)

  const groups = []

  const entities = index.entities
    .filter((entity) => match(entityLabel(entity)) || match(entity.canonical_id))
    .slice(0, LIMIT_PER_GROUP)
    .map((entity) => ({
      id: `entity:${entity.canonical_id}`,
      kind: 'entity',
      label: entityLabel(entity),
      hint: `${entityMeta(entity.entity_type).label} · ${
        (index.edgesByEntity.get(entity.canonical_id) ?? []).length
      } links`,
      icon: entityIcon(entity.entity_type),
      color: ENTITY_HEX[entity.entity_type],
      payload: entity.canonical_id,
    }))
  if (entities.length) groups.push({ title: 'Entities', items: entities })

  const relationships = index.relationships
    .filter((relationship) => {
      const from = index.labelOf(relationship.from_entity_id)
      const to = index.labelOf(relationship.to_entity_id)
      return match(from) || match(to) || match(relationship.relationship_type)
    })
    .slice(0, LIMIT_PER_GROUP)
    .map((relationship) => ({
      id: `relationship:${relationship.relationship_id}`,
      kind: 'relationship',
      label: `${index.labelOf(relationship.from_entity_id)} → ${index.labelOf(
        relationship.to_entity_id,
      )}`,
      hint: `${relationshipLabel(relationship.relationship_type)}${
        relationship.analyst_created ? ' · analyst created' : ''
      }`,
      icon: 'link',
      payload: relationship.relationship_id,
    }))
  if (relationships.length) groups.push({ title: 'Relationships', items: relationships })

  const leads = (intel?.leads?.leads ?? [])
    .filter((lead) => match(lead.subject_labels.join(' ')) || match(lead.lead_type))
    .slice(0, LIMIT_PER_GROUP)
    .map((lead) => ({
      id: `lead:${lead.lead_id}`,
      kind: 'lead',
      label: lead.subject_labels.join(', '),
      hint: `${priorityMeta(lead.network_priority).label} · ${
        LEAD_TYPE_LABEL[lead.lead_type] ?? lead.lead_type
      }`,
      icon: 'leads',
      color: priorityMeta(lead.network_priority).color,
      payload: lead.subject_entity_ids[0],
    }))
  if (leads.length) groups.push({ title: 'Leads', items: leads })

  if (needle) {
    const evidence = (index.evidenceById ? [...index.evidenceById.values()] : [])
      .filter((row) => match(row.snippet) || match(row.record_id))
      .slice(0, LIMIT_PER_GROUP)
      .map((row) => ({
        id: `evidence:${row.provenance_id}`,
        kind: 'evidence',
        label: row.snippet ? `“${row.snippet}”` : row.record_id,
        hint: `${index.documentById.get(row.document_id)?.title ?? row.source_record_id} · ${formatDate(
          row.observed_at,
        )}`,
        icon: 'document',
        payload: row.provenance_id,
      }))
    if (evidence.length) groups.push({ title: 'Evidence', items: evidence })
  }

  const pages = PAGES.filter((page) => match(page.label)).map((page) => ({
    id: page.id,
    kind: 'page',
    label: page.label,
    hint: 'Go to page',
    icon: page.icon,
    payload: page.to,
  }))
  if (pages.length) groups.push({ title: 'Go to', items: pages })

  return groups
}

export function CommandPalette() {
  const { index, intel, select, selectEntity, setTrace } = useInvestigation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [term, setTerm] = useState('')
  const [cursor, setCursor] = useState(0)
  const listRef = useRef(null)

  useEffect(() => {
    const onKey = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((value) => !value)
        setTerm('')
        setCursor(0)
      }
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const groups = useMemo(
    () => (open ? buildResults(term, index, intel.data) : []),
    [open, term, index, intel.data],
  )
  const flat = useMemo(() => groups.flatMap((group) => group.items), [groups])

  useEffect(() => {
    setCursor(0)
  }, [term])

  useEffect(() => {
    listRef.current
      ?.querySelector('[data-active="true"]')
      ?.scrollIntoView({ block: 'nearest' })
  }, [cursor, groups])

  if (!open) return null

  const choose = (item) => {
    setOpen(false)
    switch (item.kind) {
      case 'entity':
      case 'lead':
        selectEntity(item.payload, 'command')
        navigate('/network')
        break
      case 'relationship':
        select('relationship', item.payload, 'command')
        navigate('/network')
        break
      case 'evidence':
        select('evidence', item.payload, 'command')
        navigate('/evidence')
        break
      case 'page':
        setTrace((current) => ({ ...current, active: false }))
        navigate(item.payload)
        break
      default:
        break
    }
  }

  const onKeyDown = (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setCursor((value) => Math.min(flat.length - 1, value + 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setCursor((value) => Math.max(0, value - 1))
    } else if (event.key === 'Enter' && flat[cursor]) {
      event.preventDefault()
      choose(flat[cursor])
    }
  }

  let running = -1

  return (
    <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="palette__scrim" onClick={() => setOpen(false)} />
      <div className="palette__panel">
        <div className="palette__search">
          <Icon name="search" size={14} />
          <input
            className="palette__input"
            placeholder="Search this investigation"
            value={term}
            autoFocus
            onChange={(event) => setTerm(event.target.value)}
            onKeyDown={onKeyDown}
            aria-label="Search this investigation"
          />
          <kbd className="palette__kbd">Esc</kbd>
        </div>

        <div className="palette__results scroll" ref={listRef}>
          {flat.length === 0 ? (
            <p className="palette__none">Nothing in this investigation matches “{term}”.</p>
          ) : (
            groups.map((group) => (
              <div className="palette__group" key={group.title}>
                <p className="eyebrow palette__grouptitle">{group.title}</p>
                {group.items.map((item) => {
                  running += 1
                  const position = running
                  return (
                    <button
                      key={item.id}
                      type="button"
                      data-active={position === cursor}
                      className={`palette__item${position === cursor ? ' is-active' : ''}`}
                      onMouseEnter={() => setCursor(position)}
                      onClick={() => choose(item)}
                    >
                      <span
                        className="palette__icon"
                        style={item.color ? { color: item.color } : undefined}
                      >
                        <Icon name={item.icon} size={13} strokeWidth={1.5} />
                      </span>
                      <span className="palette__label truncate">{item.label}</span>
                      <span className="palette__hint truncate">{item.hint}</span>
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        <footer className="palette__foot">
          <span>
            <kbd className="palette__kbd">↑</kbd>
            <kbd className="palette__kbd">↓</kbd> navigate
          </span>
          <span>
            <kbd className="palette__kbd">↵</kbd> open
          </span>
          <span className="palette__spacer" />
          <span>Searching the loaded case only</span>
        </footer>
      </div>
    </div>
  )
}

export default CommandPalette
