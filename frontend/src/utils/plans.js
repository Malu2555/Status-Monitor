// Plan catalogue for the marketing pricing cards and the in-app upgrade card.
//
// Prices live here for *display* only — Polar.sh is the source of truth for what
// is actually charged (POLAR_PRODUCT_PRO / POLAR_PRODUCT_BUSINESS on the API).
//
// Paid tiers differ from Free by **capacity and check frequency only** — never by
// locking features. Every monitoring capability (SSL/domain expiry, broken-link
// scanning, multi-region runners, webhook/chat alerts) works on Free and in the
// open-source build. Keep the feature lists below limited to the caps actually
// enforced in `backend/billing/services.py::PLANS` (monitors, min_interval,
// status_pages, channels). `history_days` is shown for information.

export const COMING_SOON_LABEL = 'Coming soon'

export const PLANS = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    features: ['1 monitor', '5-minute checks', '1 status page', '2 alert channels', '30-day history'],
    cta: 'Create free account',
    featured: false,
    badge: '',
    comingSoon: false,
    query: {},
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '$19',
    features: ['10 monitors', '1-minute checks', '3 status pages', '10 alert channels', '90-day history'],
    cta: 'Start with Pro',
    featured: true,
    badge: 'Most Popular',
    comingSoon: false,
    query: { plan: 'pro' },
  },
  {
    id: 'business',
    name: 'Business',
    price: '$49',
    features: ['50 monitors', '1-minute checks', 'Unlimited status pages', 'Unlimited alert channels', '365-day history'],
    cta: 'Start with Business',
    featured: false,
    badge: '',
    comingSoon: false,
    query: { plan: 'business' },
  },
]

export function planById(id) {
  // Look a plan up by its API identifier ('free' | 'pro' | 'business').
  return PLANS.find((plan) => plan.id === id)
}
