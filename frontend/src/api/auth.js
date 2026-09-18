// Auth endpoints (register/login/logout/me). Login/register responses include
// the access token AND set the httpOnly refresh cookie.

import { apiFetch } from './client'

export const register = (payload) => apiFetch('/auth/register', { method: 'POST', body: payload, auth: false })

export const login = (payload) => apiFetch('/auth/login', { method: 'POST', body: payload, auth: false })

export const logout = () => apiFetch('/auth/logout', { method: 'POST' })

export const me = () => apiFetch('/auth/me')
