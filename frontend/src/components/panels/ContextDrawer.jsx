/*
 * The contextual surface.
 *
 * It exists only when the investigator has selected something. There is no
 * permanent side panel waiting to be filled, because an empty inspector teaches
 * nothing and takes space the graph should have.
 */

import Icon from '../common/Icon.jsx'
import EntityInspector from './EntityInspector.jsx'
import RelationshipInspector from './RelationshipInspector.jsx'
import EvidenceInspector from './EvidenceInspector.jsx'
import PathPanel from './PathPanel.jsx'
import './panels.css'

const KIND_LABEL = {
  entity: 'Entity',
  relationship: 'Relationship',
  evidence: 'Evidence',
  path: 'Path trace',
}

export function ContextDrawer({
  selection,
  index,
  intel,
  inline = false,
  onClose,
  onSelectEntity,
  onSelectRelationship,
  onOpenEvidence,
  onTraceFrom,
  onCreateConnection,
  pathProps,
}) {
  if (!selection?.kind) return null

  return (
    <aside className={`drawer${inline ? ' drawer--inline' : ''}`} aria-label="Investigation context">
      <div className="drawer__bar">
        <span className="drawer__kind">{KIND_LABEL[selection.kind] ?? 'Context'}</span>
        {selection.origin ? (
          <span className="mono" style={{ color: 'var(--text-muted)' }}>
            via {selection.origin}
          </span>
        ) : null}
        <button
          type="button"
          className="btn btn--ghost btn--icon btn--sm"
          onClick={onClose}
          aria-label="Close context panel"
        >
          <Icon name="close" size={12} />
        </button>
      </div>

      {selection.kind === 'entity' ? (
        <EntityInspector
          entityId={selection.id}
          index={index}
          intel={intel}
          onSelectEntity={onSelectEntity}
          onSelectRelationship={onSelectRelationship}
          onOpenEvidence={onOpenEvidence}
          onTraceFrom={onTraceFrom}
          onCreateConnection={onCreateConnection}
        />
      ) : null}

      {selection.kind === 'relationship' ? (
        <RelationshipInspector
          relationshipId={selection.id}
          index={index}
          onSelectEntity={onSelectEntity}
          onSelectRelationship={onSelectRelationship}
          onOpenEvidence={onOpenEvidence}
        />
      ) : null}

      {selection.kind === 'evidence' ? (
        <EvidenceInspector
          provenanceId={selection.id}
          index={index}
          onSelectEntity={onSelectEntity}
          onSelectRelationship={onSelectRelationship}
        />
      ) : null}

      {selection.kind === 'path' ? <PathPanel index={index} {...pathProps} /> : null}
    </aside>
  )
}

export default ContextDrawer
