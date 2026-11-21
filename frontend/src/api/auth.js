// Auth endpoints (register/login/logout/me). Login/register responses include
// the access token AND set the httpOnly refresh cookie.

import { apiFetch } from './client'

export const register = (payload) => apiFetch('/auth/register', { method: 'POST', body: payload, auth: false })

export const login = (payload) => apiFetch('/auth/login', { method: 'POST', body: payload, auth: false })

export const logout = () => apiFetch('/auth/logout', { method: 'POST' })

export const me = () => apiFetch('/auth/me')

// Confirms a signup-verification or pending email-change link.
export const verifyEmail = (token) =>
  apiFetch('/auth/verify-email', { method: 'POST', body: { token }, auth: false })

// Opt-in TOTP two-factor authentication.
export const otpStatus = () => apiFetch('/auth/otp/status')
export const otpEnroll = () => apiFetch('/auth/otp/enroll', { method: 'POST' })
export const otpActivate = (code) => apiFetch('/auth/otp/activate', { method: 'POST', body: { code } })
export const otpDisable = (code) => apiFetch('/auth/otp/disable', { method: 'POST', body: { code } })

// Programmatic access tokens (sent as X-API-Key).
export const listTokens = () => apiFetch('/auth/tokens')
export const createToken = (payload) => apiFetch('/auth/tokens', { method: 'POST', body: payload })
export const revokeToken = (id) => apiFetch(`/auth/tokens/${id}`, { method: 'DELETE' })

// 2FA recovery codes.
export const getRecoveryCodes = () => apiFetch('/auth/otp/recovery-codes')
export const regenerateRecoveryCodes = (code) =>
  apiFetch('/auth/otp/recovery-codes/regenerate', { method: 'POST', body: { code } })
