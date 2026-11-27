import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { SITE_DESCRIPTION, SITE_IMAGE, SITE_NAME, absoluteUrl } from '../utils/site'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/LandingView.vue'),
    meta: { landing: true, title: 'All-in-One Website & Uptime Monitoring' },
  },
  {
    path: '/status',
    name: 'status',
    component: () => import('../views/PublicStatusView.vue'),
    meta: {
      title: 'Live status',
      description:
        'Live uptime of Status Monitor and every service it monitors, refreshed every minute.',
    },
  },
  {
    path: '/p/:slug',
    name: 'statuspage',
    component: () => import('../views/StatusPageView.vue'),
    meta: {
      title: 'Status page',
      description: 'Current service status, uptime history and past incidents.',
    },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: 'Log in' },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/RegisterView.vue'),
    meta: { title: 'Create account' },
  },
  {
    path: '/verify-email',
    name: 'verify-email',
    component: () => import('../views/VerifyEmailView.vue'),
    meta: { title: 'Verify email' },
  },
  {
    path: '/terms',
    name: 'terms',
    component: () => import('../views/LegalView.vue'),
    props: { slug: 'terms' },
    meta: {
      title: 'Terms of Service',
      description: 'The terms that govern your use of Status Monitor.',
    },
  },
  {
    path: '/privacy',
    name: 'privacy',
    component: () => import('../views/LegalView.vue'),
    props: { slug: 'privacy' },
    meta: {
      title: 'Privacy Policy',
      description: 'What Status Monitor stores, why it stores it, and how long it is kept.',
    },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/security',
    name: 'security',
    component: () => import('../views/SecurityView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/status-pages',
    name: 'statuspages',
    component: () => import('../views/StatusPagesView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/notifications',
    name: 'notifications',
    component: () => import('../views/NotificationsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/maintenance',
    name: 'maintenance',
    component: () => import('../views/MaintenanceView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/account',
    name: 'account',
    component: () => import('../views/AccountView.vue'),
    meta: { requiresAuth: true },
  },
]

// Credential/form pages: reachable, but never indexed.
const NOINDEX_ROUTES = new Set(['login', 'register', 'verify-email', 'reset-password'])

function upsertMeta(attr, key, content) {
  // Keep exactly one tag per key, appending it on first use.
  const existing = document.head.querySelector(`meta[${attr}="${key}"]`)
  if (!content) {
    existing?.remove()
    return
  }
  if (existing) {
    existing.setAttribute('content', content)
    return
  }
  const tag = document.createElement('meta')
  tag.setAttribute(attr, key)
  tag.setAttribute('content', content)
  document.head.appendChild(tag)
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth', top: 84 }
    return { top: 0 }
  },
})

router.afterEach((to) => {
  const meta = to.meta || {}
  document.title = meta.title ? `${meta.title} · ${SITE_NAME}` : SITE_NAME

  // Per-route SEO: public pages stay indexable with their own canonical;
  // anything behind auth (or a credential form) is kept out of the index.
  const description = meta.description || SITE_DESCRIPTION
  const url = absoluteUrl(to.path)
  const noindex = Boolean(meta.requiresAuth) || NOINDEX_ROUTES.has(to.name)

  upsertMeta('name', 'description', description)
  upsertMeta('name', 'robots', noindex ? 'noindex, nofollow' : 'index, follow')
  upsertMeta('name', 'twitter:title', document.title)
  upsertMeta('name', 'twitter:description', description)
  upsertMeta('name', 'twitter:image', absoluteUrl(SITE_IMAGE))
  upsertMeta('property', 'og:title', document.title)
  upsertMeta('property', 'og:description', description)
  upsertMeta('property', 'og:url', url)
  upsertMeta('property', 'og:image', absoluteUrl(SITE_IMAGE))

  let canonical = document.head.querySelector('link[rel="canonical"]')
  if (!canonical) {
    canonical = document.createElement('link')
    canonical.setAttribute('rel', 'canonical')
    document.head.appendChild(canonical)
  }
  canonical.setAttribute('href', url)
})

// A readable cookie exists whenever a session may be present (it is set and
// cleared alongside the httpOnly refresh cookie). Using its presence lets us
// bootstrap on public routes only for returning users — so a logged-in user
// opening /p/<slug> in a new window still restores the session (and shows the
// app navbar), while anonymous visitors get no auth round-trip.
function mayHaveSession() {
  return /(?:^|;\s*)sm_csrf=/.test(document.cookie)
}

// Auth guard: bootstraps the session once (silent refresh via httpOnly cookie),
// then enforces route access.
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready && (to.meta.requiresAuth || mayHaveSession())) await auth.bootstrap()
  if (to.meta.requiresAuth && !auth.isAuthenticated) return { name: 'login' }
  if ((to.name === 'login' || to.name === 'register') && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
})

export default router

