/*
 * The entity taxonomy as raw geometry.
 *
 * These path strings are the single source for both the React icon set and the
 * glyphs painted inside graph nodes, so the mark for a person is literally the
 * same drawing in the rail, in a list, and on the canvas. Each is drawn on a
 * 16-unit grid.
 */

export const ENTITY_GLYPH_PATHS = {
  person: ['M8 5.6 m-2.5 0 a2.5 2.5 0 1 0 5 0 a2.5 2.5 0 1 0 -5 0', 'M2.9 13.4c.5-2.6 2.6-4 5.1-4s4.6 1.4 5.1 4'],
  organization: [
    'M2.6 13.6V4.2l5.1-1.8v11.2',
    'M7.7 6.5h5.7v7.1',
    'M1.5 13.6h13',
  ],
  location: [
    'M8 14.2s4.6-4.1 4.6-7.5a4.6 4.6 0 1 0-9.2 0c0 3.4 4.6 7.5 4.6 7.5Z',
    'M8 6.6 m-1.7 0 a1.7 1.7 0 1 0 3.4 0 a1.7 1.7 0 1 0 -3.4 0',
  ],
  phone: ['M6.2 1.9h3.6a1.6 1.6 0 0 1 1.6 1.6v9a1.6 1.6 0 0 1-1.6 1.6H6.2a1.6 1.6 0 0 1-1.6-1.6v-9a1.6 1.6 0 0 1 1.6-1.6Z', 'M6.9 4.1h2.2'],
  vehicle: [
    'M2 10.4V8.2l1.5-3.3a1.4 1.4 0 0 1 1.3-.8h6.4a1.4 1.4 0 0 1 1.3.8L14 8.2v2.2',
    'M2 10.4h12',
    'M3.3 8.1h9.4',
  ],
  incident: ['M8 1.9 14.1 8 8 14.1 1.9 8 8 1.9Z', 'M8 5.4v3.1', 'M8 10.85v.2'],
}

/**
 * A glyph as a data URI, for renderers that take an image rather than a node.
 * The stroke colour is baked in because the canvas cannot resolve a CSS
 * variable at paint time.
 */
export function glyphDataUri(type, color, strokeWidth = 1.45) {
  const paths = ENTITY_GLYPH_PATHS[type] ?? ['M8 8 m-5 0 a5 5 0 1 0 10 0 a5 5 0 1 0 -10 0']
  const body = paths
    .map(
      (d) =>
        `<path d="${d}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round"/>`,
    )
    .join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">${body}</svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}
