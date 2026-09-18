// Billing endpoints: Stripe checkout, customer portal, plan summary.

import { apiFetch } from './client'

export const checkout = (plan) => apiFetch('/billing/checkout', { method: 'POST', body: { plan } })

export const portal = () => apiFetch('/billing/portal', { method: 'POST' })

export const summary = () => apiFetch('/billing/summary')
