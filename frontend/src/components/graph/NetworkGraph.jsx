/*
 * The investigation graph.
 *
 * Everything drawn here comes from the persisted case: nodes are the resolved
 * entities, edges are the projected relationships, edge colour is the context
 * Stage C classified, and edge dash is the assertion the backend recorded. No
 * element is synthetic and no position is authored.
 *
 * Emphasis is the whole interaction model. Hovering previews a neighbourhood,
 * selecting anchors one, tracing walks a path hop by hop, and everything not
 * currently relevant recedes rather than disappearing - an investigator needs
 * to see that the rest of the network is still there.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import { ENTITY_HEX, ENTITY_SOFT_HEX, entityLabel, relationshipLabel } from '../../lib/domain.js'
import { glyphDataUri } from '../../lib/glyphs.js'
import {
  LAYOUTS,
  NODE_SHAPE,
  buildStylesheet,
  contextHex,
  edgeWidth,
  nodeSize,
} from '../../lib/graphStyle.js'
import { toDate } from '../../lib/format.js'
import './graph.css'

cytoscape.use(fcose)

const glyphCache = new Map()
const glyphFor = (type) => {
  if (!glyphCache.has(type)) glyphCache.set(type, glyphDataUri(type, ENTITY_HEX[type] ?? '#858b87'))
  return glyphCache.get(type)
}

/* A small graph will happily fit at 3x, which turns labels into headlines and
 * nodes into balloons. Fitting is still what we want; it just stops at the
 * point where the map still reads as a map. */
const MAX_FIT_ZOOM = 1.15

function fitWithin(cy, padding = 56) {
  cy.fit(undefined, padding)
  if (cy.zoom() > MAX_FIT_ZOOM) {
    cy.zoom({ level: MAX_FIT_ZOOM, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
    cy.center()
  }
}

/** Translate the case into cytoscape elements. Pure: same case, same graph. */
function buildElements(index) {
  const degrees = new Map()
  for (const relationship of index.relationships) {
    degrees.set(relationship.from_entity_id, (degrees.get(relationship.from_entity_id) ?? 0) + 1)
    degrees.set(relationship.to_entity_id, (degrees.get(relationship.to_entity_id) ?? 0) + 1)
  }
  const maxDegree = Math.max(1, ...degrees.values())

  const nodes = index.entities.map((entity) => {
    const type = entity.entity_type
    const degree = degrees.get(entity.canonical_id) ?? 0
    return {
      group: 'nodes',
      data: {
        id: entity.canonical_id,
        label: entityLabel(entity),
        type,
        shape: NODE_SHAPE[type] ?? 'ellipse',
        color: ENTITY_HEX[type] ?? '#858b87',
        soft: ENTITY_SOFT_HEX[type] ?? '#f2f4f1',
        glyph: glyphFor(type),
        degree,
        size: nodeSize(degree, maxDegree),
      },
    }
  })

  const known = new Set(index.entities.map((entity) => entity.canonical_id))
  const edges = index.relationships
    .filter(
      (relationship) =>
        known.has(relationship.from_entity_id) && known.has(relationship.to_entity_id),
    )
    .map((relationship) => {
      const classified = index.contextByRelationship.get(relationship.relationship_id)
      const context = classified?.context ?? 'unknown'
      const width = edgeWidth(relationship.evidence_count)
      /* Only a stated occurrence date places an edge in time; see the note on
       * `events` in the investigation index. */
      const occurred = toDate(relationship.occurred_at)
      return {
        group: 'edges',
        data: {
          id: relationship.relationship_id,
          source: relationship.from_entity_id,
          target: relationship.to_entity_id,
          type: relationship.relationship_type,
          typeLabel: relationshipLabel(relationship.relationship_type),
          context,
          color: contextHex(context),
          assertion: relationship.assertion_type,
          analyst: relationship.analyst_created,
          lineStyle: relationship.assertion_type === 'observed' ? 'solid' : 'dashed',
          arrow: DIRECTED.has(relationship.relationship_type) ? 'triangle' : 'none',
          width,
          widthEmphasis: width + 1.2,
          widthPath: width + 1.8,
          at: occurred ? occurred.getTime() : null,
        },
        classes: relationship.analyst_created ? 'analyst' : '',
      }
    })

  return [...nodes, ...edges]
}

/* Relationship types whose direction the source actually states. Symmetric
 * types are drawn without an arrowhead rather than implying a direction the
 * record does not carry. */
const DIRECTED = new Set(['located_at', 'owns', 'uses', 'member_of', 'involved_in', 'transacted_with'])

export function NetworkGraph({
  index,
  selection,
  onSelectEntity,
  onSelectRelationship,
  onClearSelection,
  onHoverEntity,
  filters,
  timeRange,
  activePath,
  traceEndpoints,
  traceActive,
  layoutName,
  focusToken,
  onReady,
}) {
  const containerRef = useRef(null)
  const cyRef = useRef(null)
  const handlers = useRef({})

  handlers.current = { onSelectEntity, onSelectRelationship, onClearSelection, onHoverEntity }

  const elements = useMemo(() => buildElements(index), [index])

  /* ---- create once, then keep the same instance across data updates ---- */
  useEffect(() => {
    if (!containerRef.current) return undefined
    const cy = cytoscape({
      container: containerRef.current,
      style: buildStylesheet(),
      elements: [],
      minZoom: 0.18,
      maxZoom: 3.2,
      wheelSensitivity: 0.22,
      boxSelectionEnabled: false,
      autoungrabify: false,
      selectionType: 'single',
    })
    cyRef.current = cy

    cy.on('tap', 'node', (event) => handlers.current.onSelectEntity?.(event.target.id()))
    cy.on('tap', 'edge', (event) => handlers.current.onSelectRelationship?.(event.target.id()))
    cy.on('tap', (event) => {
      if (event.target === cy) handlers.current.onClearSelection?.()
    })
    cy.on('mouseover', 'node', (event) => {
      applyHover(cy, event.target)
      handlers.current.onHoverEntity?.(event.target.id())
    })
    cy.on('mouseout', 'node', () => {
      clearHover(cy)
      handlers.current.onHoverEntity?.(null)
    })
    cy.on('mouseover', 'edge', (event) => event.target.addClass('near'))
    cy.on('mouseout', 'edge', (event) => {
      if (!event.target.hasClass('sticky-near')) event.target.removeClass('near')
    })

    /* The canvas shrinks when a context panel opens. Cytoscape has to be told,
     * or half the network ends up behind the panel. */
    const observer = new ResizeObserver(() => {
      cy.resize()
    })
    observer.observe(containerRef.current)

    /* A handle on the live instance during development, so the graph can be
     * inspected and driven from the console or a browser test. Never exposed in
     * a production build. */
    if (import.meta.env.DEV) window.__silentTraceCy = cy

    onReady?.(cy)
    return () => {
      observer.disconnect()
      cy.destroy()
      cyRef.current = null
      if (import.meta.env.DEV && window.__silentTraceCy === cy) delete window.__silentTraceCy
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ---- data: replace elements and re-run the layout ---- */
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    const previousPositions = new Map()
    cy.nodes().forEach((node) => previousPositions.set(node.id(), { ...node.position() }))

    cy.batch(() => {
      cy.elements().remove()
      cy.add(elements)
    })

    /* Keep positions for entities that were already on screen so an added
     * relationship does not reshuffle the whole map under the investigator. */
    let reused = 0
    cy.nodes().forEach((node) => {
      const previous = previousPositions.get(node.id())
      if (previous) {
        node.position(previous)
        reused += 1
      }
    })

    const full = true
    if (full) {
      const layout = cy.layout({
        ...(LAYOUTS[layoutName]?.options ?? LAYOUTS.fcose.options),
        fit: false,
      })
      layout.one('layoutstop', () => fitWithin(cy))
      layout.run()
    } else {
      fitWithin(cy)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements])

  /* ---- layout changes requested from the toolbar ---- */
  const layoutRef = useRef(layoutName)
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || cy.nodes().length === 0) return
    if (layoutRef.current === layoutName) return
    layoutRef.current = layoutName
    const config = LAYOUTS[layoutName] ?? LAYOUTS.fcose
    const options = { ...config.options, fit: false }
    if (layoutName === 'breadthfirst') {
      const root = selection?.kind === 'entity' ? selection.id : null
      if (root && cy.getElementById(root).nonempty()) options.roots = [root]
    }
    if (layoutName === 'circle') {
      options.sort = (a, b) => String(a.data('type')).localeCompare(String(b.data('type')))
    }
    const layout = cy.layout(options)
    layout.one('layoutstop', () => fitWithin(cy))
    layout.run()
  }, [layoutName, selection])

  /* ---- filters and the timeline window ---- */
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    const typeSet = new Set(filters.entityTypes)
    const contextSet = new Set(filters.contexts)
    const term = filters.search.trim().toLowerCase()
    const [from, to] = timeRange ?? []
    const fromMs = from ? from.getTime() : null
    const toMs = to ? to.getTime() : null

    cy.batch(() => {
      cy.nodes().forEach((node) => {
        const typeOk = typeSet.size === 0 || typeSet.has(node.data('type'))
        const searchOk = !term || String(node.data('label')).toLowerCase().includes(term)
        node.toggleClass('filtered', !(typeOk && searchOk))
      })
      cy.edges().forEach((edge) => {
        const endpointsVisible =
          !edge.source().hasClass('filtered') && !edge.target().hasClass('filtered')
        const contextOk = contextSet.size === 0 || contextSet.has(edge.data('context'))
        const assertionOk =
          filters.assertion === 'all' ||
          (filters.assertion === 'analyst' && edge.data('analyst')) ||
          (filters.assertion !== 'analyst' && edge.data('assertion') === filters.assertion)
        edge.toggleClass('filtered', !(endpointsVisible && contextOk && assertionOk))

        const at = edge.data('at')
        const inWindow =
          fromMs === null || at === null ? true : at >= fromMs && at <= toMs
        edge.toggleClass('outoftime', !inWindow)
      })
    })
  }, [filters, timeRange, elements])

  /* ---- selection emphasis ---- */
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => {
      cy.elements().removeClass('selected near dim')
      if (!selection?.id) return

      if (selection.kind === 'entity') {
        const node = cy.getElementById(selection.id)
        if (node.empty()) return
        const neighbourhood = node.closedNeighborhood()
        cy.elements().difference(neighbourhood).addClass('dim')
        neighbourhood.addClass('near')
        node.removeClass('near').addClass('selected')
      } else if (selection.kind === 'relationship') {
        const edge = cy.getElementById(selection.id)
        if (edge.empty()) return
        const scope = edge.union(edge.connectedNodes())
        cy.elements().difference(scope).addClass('dim')
        edge.connectedNodes().addClass('near')
        edge.addClass('selected')
      }
    })
  }, [selection, elements])

  /* ---- recentre on the selected entity ---- */
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !focusToken) return
    if (selection?.kind !== 'entity' || !selection.id) return
    const node = cy.getElementById(selection.id)
    if (node.empty()) return
    cy.animate(
      {
        center: { eles: node.closedNeighborhood() },
        zoom: Math.min(MAX_FIT_ZOOM, Math.max(0.6, cy.zoom())),
      },
      { duration: 260, easing: 'ease-out' },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusToken])

  /* ---- the trace: a path drawn hop by hop ---- */
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('onpath labelled endpoint')

    for (const endpoint of traceEndpoints ?? []) {
      if (!endpoint) continue
      cy.getElementById(endpoint).addClass('endpoint')
    }

    if (!activePath?.edges?.length) return

    const timers = []
    cy.elements().addClass('dim')
    const first = cy.getElementById(activePath.edges[0].from_entity_id)
    first.removeClass('dim').addClass('onpath')

    activePath.edges.forEach((hop, position) => {
      timers.push(
        window.setTimeout(() => {
          const alive = cyRef.current
          if (!alive) return
          const edge = alive.getElementById(hop.relationship_id)
          const target = alive.getElementById(hop.to_entity_id)
          edge.removeClass('dim').addClass('onpath labelled')
          target.removeClass('dim').addClass('onpath')
        }, 90 + position * 180),
      )
    })

    timers.push(
      window.setTimeout(() => {
        const alive = cyRef.current
        if (!alive) return
        const path = alive.elements('.onpath')
        if (path.nonempty()) {
          /* Frame the route, but keep the same zoom ceiling as everywhere else:
           * a two-hop path would otherwise fill the canvas at 3x. */
          alive.animate(
            { fit: { eles: path, padding: 110 } },
            {
              duration: 320,
              easing: 'ease-out',
              complete: () => {
                if (alive.zoom() > MAX_FIT_ZOOM) {
                  alive.zoom({
                    level: MAX_FIT_ZOOM,
                    renderedPosition: { x: alive.width() / 2, y: alive.height() / 2 },
                  })
                  alive.center(path)
                }
              },
            },
          )
        }
      }, 120 + activePath.edges.length * 180),
    )

    return () => timers.forEach((timer) => window.clearTimeout(timer))
  }, [activePath, traceEndpoints, elements])

  /* ---- while tracing, the cursor says the canvas is in pick mode ---- */
  useEffect(() => {
    containerRef.current?.classList.toggle('is-tracing', Boolean(traceActive))
  }, [traceActive])

  const handleContext = useCallback((event) => event.preventDefault(), [])

  return <div ref={containerRef} className="graphcanvas" onContextMenu={handleContext} />
}

function applyHover(cy, node) {
  if (node.hasClass('selected')) return
  cy.batch(() => {
    node.addClass('hover')
    node.neighborhood().addClass('near')
  })
}

function clearHover(cy) {
  cy.batch(() => {
    cy.nodes().removeClass('hover')
    if (!cy.elements('.selected').nonempty()) {
      cy.elements().removeClass('near')
    } else {
      const selected = cy.elements('.selected')
      const keep = selected.closedNeighborhood()
      cy.elements().difference(keep).removeClass('near')
    }
  })
}

export default NetworkGraph
