// Fetch wrapper with the JWT security model:
//  - access token: in-memory only, sent via Authorization header
//  - refresh token: httpOnly SameSite=Strict cookie (path=/api/auth), never readable by JS
//  - on 401 → one silent refresh (cookie + CSRF header) → retry the original request
//  - on refresh failure → session is cleared (via onUnauthorized hook)

import { logger } from '../utils/logger'

let accessToken = null
let onUnauthorized = null
let refreshPromise = null

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail)
    this.status = status
  }
}

export function setAccessToken(token) {
  accessToken = token
}

export function getAccessToken() {
  return accessToken
}

export function setOnUnauthorized(fn) {
  onUnauthorized = fn
}

export function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)sm_csrf=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

// POST /api/auth/refresh once; concurrent callers share a single request.
function refreshAccessToken() {
  if (!refreshPromise) {
    logger.debug('refreshing access token via httpOnly cookie')
    refreshPromise = fetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'X-CSRF-Token': getCsrfToken() },
      credentials: 'same-origin',
    })
      .then(async (res) => {
        if (!res.ok) throw new ApiError(res.status, 'Session expired')
        const data = await res.json()
        accessToken = data.access
        return data.access
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

// Turn any error body into readable text. Django Ninja returns a list of
// { loc, msg, ... } validation errors for 422; other routes return a plain
// `detail: "..."` string. Arrays/objects must be flattened here — passing them
// straight into `new Error(...)` prints the useless "[object Object]".
function describeErrorDetail(data, fallback) {
  if (!data || typeof data !== 'object') return fallback
  if (Array.isArray(data.detail)) {
    const lines = data.detail.map((err) => {
      const field = Array.isArray(err?.loc)
        ? err.loc.filter((segment) => segment !== 'body').join('.')
        : ''
      let message = ''
      if (err && typeof err.msg === 'string') {
        message = err.msg
      } else if (err != null) {
        try {
          message = JSON.stringify(err)
        } catch {
          message = String(err)
        }
      }
      if (field && message) return `${field}: ${message}`
      return message || field || 'Validation error'
    })
    const joined = lines.filter(Boolean).join('; ')
    if (joined) return joined
  }
  if (typeof data.detail === 'string' && data.detail) return data.detail
  if (data.detail) {
    try {
      return JSON.stringify(data.detail)
    } catch {
      /* fall through */
    }
  }
  if (typeof data.message === 'string' && data.message) return data.message
  return fallback
}

export async function apiFetch(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (accessToken && auth) headers.Authorization = `Bearer ${accessToken}`

  const doFetch = () =>
    fetch(`/api${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })

  let res = await doFetch()

  // Expired access token? Refresh once, then retry the original request.
  if (res.status === 401 && auth && path !== '/auth/refresh') {
    try {
      await refreshAccessToken()
      headers.Authorization = `Bearer ${accessToken}`
      res = await doFetch()
    } catch (error) {
      // Only end the session when auth was genuinely rejected (401). A
      // transient 5xx/network failure must not log the user out.
      if (error instanceof ApiError && error.status === 401) {
        accessToken = null
        logger.warn('session refresh rejected — ending session')
        if (onUnauthorized) onUnauthorized()
      }
      throw error instanceof ApiError ? error : new ApiError(401, 'Session expired')
    }
  }

  if (!res.ok) {
    logger.debug('api error', path, res.status)
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = describeErrorDetail(data, detail)
    } catch {
      /* non-JSON body — keep statusText */
    }
    // Human-friendly text for the two most common infra statuses.
    const friendly = {
      429: 'Too many requests — please wait a moment.',
      503: 'Service temporarily unavailable.',
    }[res.status]
    throw new ApiError(res.status, friendly ?? (detail || `HTTP ${res.status}`))
  }

  if (res.status === 204) return null
  const text = await res.text()
  return text ? JSON.parse(text) : null
}
