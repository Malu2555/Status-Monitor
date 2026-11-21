// Planned maintenance windows (suppress alerts while they run).
import { apiFetch } from './client'

export const listWindows = (monitorId) => apiFetch(`/monitors/${monitorId}/maintenance`)

export const createWindow = (monitorId, payload) =>
  apiFetch(`/monitors/${monitorId}/maintenance`, { method: 'POST', body: payload })

export const deleteWindow = (monitorId, windowId) =>
  apiFetch(`/monitors/${monitorId}/maintenance/${windowId}`, { method: 'DELETE' })
