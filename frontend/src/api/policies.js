// Public legal text (terms / privacy). Unauthenticated.
import { apiFetch } from './client'

export const getPolicy = (slug) => apiFetch(`/policies/${slug}`, { auth: false })
