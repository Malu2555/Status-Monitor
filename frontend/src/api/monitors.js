// Monitor endpoints: private CRUD + stats, and the free public feed.

import { apiFetch } from './client'

export const listMonitors = () => apiFetch('/monitors')

export const createMonitor = (payload) => apiFetch('/monitors', { method: 'POST', body: payload })

export const updateMonitor = (id, payload) => apiFetch(`/monitors/${id}`, { method: 'PATCH', body: payload })

export const deleteMonitor = (id) => apiFetch(`/monitors/${id}`, { method: 'DELETE' })

export const monitorStats = (id, hours = 24) => apiFetch(`/monitors/${id}/stats?hours=${hours}`)

// Public, unauthenticated
export const publicMonitors = () => apiFetch('/public/monitors', { auth: false })

export const publicMonitorDetail = (id) => apiFetch(`/public/monitors/${id}`, { auth: false })
