// Plan catalogue for the marketing pricing cards and the in-app upgrade card.
//
// Prices live here for *display* only — Polar.sh is the source of truth for what
// is actually charged (POLAR_PRODUCT_PRO / POLAR_PRODUCT_BUSINESS on the API).
//
// `comingSoon: true` keeps the price visible but disables the call to action
// while the Polar product for that plan is pending approval. Polar approves
// products one by one, so flip a single plan at a time: set it to false here,
// redeploy the SPA, and make sure the matching POLAR_PRODUCT_* env var is set.

export const COMING_SOON_LABEL = 'Coming soon'

export const PLANS = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    features: ['1 monitor', '5 min intervals', 'Public status page', 'Email alerts'],
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
    features: ['10 monitors', '1 min intervals', 'Custom status pages', 'SSL & domain monitoring'],
    cta: 'Start with Pro',
    featured: true,
    badge: 'Most Popular',
    comingSoon: true,
    query: { plan: 'pro' },
  },
  {
    id: 'business',
    name: 'Business',
    price: '$49',
    features: ['50 monitors', '1 min intervals', 'Multi-region checks', 'Webhook & chat alerts'],
    cta: 'Start with Business',
    featured: false,
    badge: '',
    comingSoon: true,
    query: { plan: 'business' },
  },
]

export function planById(id) {
  // Look a plan up by its API identifier ('free' | 'pro' | 'business').
  return PLANS.find((plan) => plan.id === id)
}
