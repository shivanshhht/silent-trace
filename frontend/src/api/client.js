/*
 * The single door to the backend.
 *
 * Every request in the application goes through `request`, so a failure is
 * shaped the same way everywhere and no component has to invent its own error
 * handling. FastAPI answers errors as `{ detail }`; that detail is what the
 * investigator sees, because it is the backend's own account of what went
 * wrong and is more useful than a status code.
 */

const BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  constructor(message, status, url) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
  }
}

async function request(path, options = {}) {
  const url = `${BASE}${path}`
  let response
  try {
    response = await fetch(url, {
      ...options,
      headers: { Accept: 'application/json', ...(options.headers ?? {}) },
    })
  } catch (cause) {
    throw new ApiError(
      'Cannot reach the Silent Trace API. Start the backend on port 8000.',
      0,
      url,
    )
  }

  if (!response.ok) {
    let detail = `Request failed with HTTP ${response.status}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail) && body.detail.length) {
        detail = body.detail.map((item) => item.msg ?? JSON.stringify(item)).join('; ')
      }
    } catch {
      /* a non-JSON error body leaves the status-code message in place */
    }
    throw new ApiError(detail, response.status, url)
  }

  if (response.status === 204) return null
  return response.json()
}

export const get = (path) => request(path)

export const post = (path, body) =>
  request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const query = (params) => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}
