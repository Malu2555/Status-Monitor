// Self-service account management.
import { apiFetch } from './client'

export const changePassword = (payload) =>
  apiFetch('/auth/change-password', { method: 'POST', body: payload })

export const changeEmail = (payload) =>
  apiFetch('/auth/change-email', { method: 'POST', body: payload })

export const revokeOtherSessions = () =>
  apiFetch('/auth/sessions/revoke-others', { method: 'POST' })

export const deleteAccount = (payload) =>
  apiFetch('/auth/me', { method: 'DELETE', body: payload })
