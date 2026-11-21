// Owner-scoped notification channels (email / webhook / Slack / Discord / Telegram).
import { apiFetch } from './client'

export const listChannels = () => apiFetch('/notifications/channels')

export const createChannel = (payload) =>
  apiFetch('/notifications/channels', { method: 'POST', body: payload })

export const updateChannel = (id, payload) =>
  apiFetch(`/notifications/channels/${id}`, { method: 'PATCH', body: payload })

export const deleteChannel = (id) =>
  apiFetch(`/notifications/channels/${id}`, { method: 'DELETE' })

export const testChannel = (id) =>
  apiFetch(`/notifications/channels/${id}/test`, { method: 'POST' })
