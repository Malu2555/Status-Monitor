// Monitor endpoints: private CRUD + stats, and the free public feed.

import { apiFetch } from './client'

export const listMonitors = () => apiFetch('/monitors')

export const getMonitor = (id) => apiFetch(`/monitors/${id}`)

export const createMonitor = (payload) => apiFetch('/monitors', { method: 'POST', body: payload })

export const updateMonitor = (id, payload) => apiFetch(`/monitors/${id}`, { method: 'PATCH', body: payload })

export const deleteMonitor = (id) => apiFetch(`/monitors/${id}`, { method: 'DELETE' })

export const monitorStats = (id, hours = 24) => apiFetch(`/monitors/${id}/stats?hours=${hours}`)

export const uptimeBuckets = (id, hours = 24, bucketHours = 1) =>
  apiFetch(`/monitors/${id}/uptime-buckets?hours=${hours}&bucket_hours=${bucketHours}`)

export const monitorRegions = (id, hours = 24) => apiFetch(`/monitors/${id}/regions?hours=${hours}`)

export const monitorSsl = (id) => apiFetch(`/monitors/${id}/ssl`)

export const listIncidents = (id, limit = 20, offset = 0) =>
  apiFetch(`/monitors/${id}/incidents?limit=${limit}&offset=${offset}`)

// Public, unauthenticated
export const publicMonitors = () => apiFetch('/public/monitors', { auth: false })

export const publicMonitorDetail = (id) => apiFetch(`/public/monitors/${id}`, { auth: false })

export const publicStatusPage = (slug) => apiFetch(`/public/statuspages/${slug}`, { auth: false })

export const monitorDomain = (id) => apiFetch(`/monitors/${id}/domain`)

export const monitorCrawl = (id) => apiFetch(`/monitors/${id}/crawl`)

export const runCrawl = (id) => apiFetch(`/monitors/${id}/crawl/run`, { method: 'POST' })
