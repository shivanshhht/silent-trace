/*
 * The graph's visual language.
 *
 * The intent is information cartography, not decoration. A node is a small
 * white plate with a coloured border, a type glyph and a readable label: the
 * kind of mark a map or a schematic uses, where meaning is carried by shape and
 * placement rather than by glow. Nothing pulses, nothing halos, and no element
 * is coloured unless the colour says something.
 *
 * Three channels carry the semantics, and all three are readable at once:
 *   shape + glyph -> what kind of entity this is
 *   edge colour   -> the context the relationship was recorded in
 *   edge dash     -> how the claim is held (observed, inferred, analyst)
 */

import { CONTEXT_META } from './domain.js'

/* Silhouettes chosen to stay distinguishable at small sizes and at a glance. */
export const NODE_SHAPE = {
  person: 'ellipse',
  organization: 'round-rectangle',
  location: 'round-diamond',
  phone: 'round-tag',
  vehicle: 'round-hexagon',
  incident: 'cut-rectangle',
}

const INK = '#171918'
const ANALYST = '#6d5ba6'
const TRACE = '#a8541a'

/** Node diameter grows with degree, but only within a narrow band: a hub should
 *  read as larger, not as a different kind of object. */
export function nodeSize(degree, maxDegree) {
  const span = Math.max(1, maxDegree)
  const ratio = Math.min(1, (degree ?? 0) / span)
  return 30 + Math.round(ratio * 20)
}

export function edgeWidth(evidenceCount) {
  return 1 + Math.min(1.6, Math.log2(1 + (evidenceCount ?? 1)) * 0.8)
}

export const contextHex = (context) => (CONTEXT_META[context] ?? CONTEXT_META.unknown).hex

export function buildStylesheet() {
  return [
    /* ------------------------------------------------------------- nodes */
    {
      selector: 'node',
      style: {
        width: 'data(size)',
        height: 'data(size)',
        shape: 'data(shape)',
        'background-color': '#ffffff',
        'background-image': 'data(glyph)',
        'background-width': '46%',
        'background-height': '46%',
        'background-position-x': '50%',
        'background-position-y': '50%',
        'background-clip': 'none',
        'border-width': 1.4,
        'border-color': 'data(color)',
        'border-opacity': 1,
        label: 'data(label)',
        'font-family': 'Inter, system-ui, sans-serif',
        'font-size': 10.5,
        'font-weight': 500,
        color: INK,
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 5,
        'text-max-width': 108,
        'text-wrap': 'ellipsis',
        'text-background-color': '#fbfcfa',
        'text-background-opacity': 0.82,
        'text-background-padding': 2,
        'text-background-shape': 'roundrectangle',
        'overlay-opacity': 0,
        'transition-property': 'border-width, border-color, opacity, background-color, width, height',
        'transition-duration': '180ms',
        'transition-timing-function': 'ease-in-out',
      },
    },
    {
      /* the analytical accent: a filled plate marks an entity Stage C flagged */
      selector: 'node.flagged',
      style: {
        'background-color': 'data(soft)',
        'border-width': 1.6,
      },
    },
    {
      selector: 'node.hover',
      style: {
        'border-width': 2.4,
        'font-weight': 600,
        'text-background-opacity': 0.95,
        'z-index': 30,
      },
    },
    {
      selector: 'node.near',
      style: {
        'border-width': 1.8,
        'z-index': 20,
      },
    },
    {
      selector: 'node.selected',
      style: {
        'border-width': 2.6,
        'border-color': INK,
        'background-color': '#ffffff',
        'font-weight': 700,
        'text-background-opacity': 1,
        'z-index': 40,
      },
    },
    {
      selector: 'node.endpoint',
      style: {
        'border-width': 2.6,
        'border-color': TRACE,
        'z-index': 38,
      },
    },
    {
      selector: 'node.onpath',
      style: {
        'border-width': 2.4,
        'border-color': TRACE,
        'background-color': '#faf3ec',
        'font-weight': 600,
        'z-index': 36,
      },
    },
    {
      selector: 'node.dim',
      style: {
        opacity: 0.24,
        'text-opacity': 0,
        'z-index': 1,
      },
    },
    {
      selector: 'node.filtered',
      style: {
        opacity: 0.1,
        'text-opacity': 0,
        events: 'no',
      },
    },

    /* ------------------------------------------------------------- edges */
    {
      selector: 'edge',
      style: {
        width: 'data(width)',
        'line-color': 'data(color)',
        'line-style': 'data(lineStyle)',
        'line-dash-pattern': [5, 4],
        'curve-style': 'bezier',
        'control-point-step-size': 34,
        opacity: 0.5,
        'target-arrow-color': 'data(color)',
        'target-arrow-shape': 'data(arrow)',
        'arrow-scale': 0.62,
        'overlay-opacity': 0,
        'transition-property': 'opacity, width, line-color',
        'transition-duration': '180ms',
        'transition-timing-function': 'ease-in-out',
      },
    },
    {
      selector: 'edge.analyst',
      style: {
        'line-color': ANALYST,
        'target-arrow-color': ANALYST,
        'line-dash-pattern': [2, 3],
        opacity: 0.75,
      },
    },
    {
      selector: 'edge.near',
      style: {
        opacity: 0.9,
        width: 'data(widthEmphasis)',
        'z-index': 15,
      },
    },
    {
      selector: 'edge.selected',
      style: {
        opacity: 1,
        width: 'data(widthEmphasis)',
        'line-color': INK,
        'target-arrow-color': INK,
        label: 'data(typeLabel)',
        'font-family': 'Inter, system-ui, sans-serif',
        'font-size': 9.5,
        'font-weight': 600,
        color: INK,
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.94,
        'text-background-padding': 3,
        'text-background-shape': 'roundrectangle',
        'text-rotation': 'autorotate',
        'z-index': 45,
      },
    },
    {
      selector: 'edge.onpath',
      style: {
        opacity: 1,
        width: 'data(widthPath)',
        'line-color': TRACE,
        'target-arrow-color': TRACE,
        'z-index': 35,
      },
    },
    {
      selector: 'edge.onpath.labelled',
      style: {
        label: 'data(typeLabel)',
        'font-family': 'Inter, system-ui, sans-serif',
        'font-size': 9.5,
        'font-weight': 600,
        color: '#7a3d12',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.94,
        'text-background-padding': 3,
        'text-background-shape': 'roundrectangle',
        'text-rotation': 'autorotate',
      },
    },
    {
      selector: 'edge.dim',
      style: {
        opacity: 0.1,
        'z-index': 0,
      },
    },
    {
      selector: 'edge.filtered',
      style: {
        opacity: 0.05,
        events: 'no',
      },
    },
    {
      /* outside the timeline window: present, but plainly not in scope */
      selector: 'edge.outoftime',
      style: {
        opacity: 0.08,
        'line-style': 'dotted',
      },
    },
  ]
}

/** Layouts offered in the toolbar. Every one is deterministic given a seed. */
export const LAYOUTS = {
  fcose: {
    label: 'Force',
    hint: 'Force-directed. Clusters that are densely linked settle together.',
    options: {
      name: 'fcose',
      quality: 'proof',
      randomize: true,
      animate: true,
      animationDuration: 480,
      animationEasing: 'ease-out',
      fit: true,
      padding: 56,
      nodeSeparation: 96,
      idealEdgeLength: 118,
      nodeRepulsion: 8200,
      gravity: 0.22,
      gravityRange: 3.2,
      numIter: 2600,
      tile: true,
      packComponents: true,
    },
  },
  concentric: {
    label: 'Priority',
    hint: 'Rings by number of relationships. The most connected entities sit at the centre.',
    options: {
      name: 'concentric',
      animate: true,
      animationDuration: 420,
      fit: true,
      padding: 56,
      minNodeSpacing: 46,
      concentric: (node) => node.data('degree') ?? 0,
      levelWidth: () => 1,
    },
  },
  breadthfirst: {
    label: 'Hierarchy',
    hint: 'Layers outward from the selected entity, one hop per row.',
    options: {
      name: 'breadthfirst',
      animate: true,
      animationDuration: 420,
      fit: true,
      padding: 56,
      spacingFactor: 1.15,
      directed: false,
      grid: true,
    },
  },
  circle: {
    label: 'Circle',
    hint: 'Every entity on one ring, grouped by type.',
    options: {
      name: 'circle',
      animate: true,
      animationDuration: 420,
      fit: true,
      padding: 56,
      spacingFactor: 1.05,
    },
  },
}
