// Status page CRUD (owner-scoped).
// Public rendering lives at /api/public/statuspages/{slug} and the SPA route /p/:slug.
import { apiFetch } from './client'

export const listStatusPages = () => apiFetch('/statuspages')

export const createStatusPage = (payload) =>
  apiFetch('/statuspages', { method: 'POST', body: payload })

export const updateStatusPage = (id, payload) =>
  apiFetch(`/statuspages/${id}`, { method: 'PATCH', body: payload })

export const deleteStatusPage = (id) => apiFetch(`/statuspages/${id}`, { method: 'DELETE' })
