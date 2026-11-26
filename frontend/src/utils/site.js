// Canonical site URL + shared SEO strings.
//
// One place to change when the custom domain goes live: set VITE_SITE_URL in
// Vercel (and keep the literal URLs in index.html in sync). Everything the app
// emits at runtime — canonical, og:url, robots — is derived from here.

export const SITE_URL = (
  import.meta.env.VITE_SITE_URL || 'https://status-monitor-alpha.vercel.app'
).replace(/\/+$/, '')

export const SITE_NAME = 'Status Monitor'
export const SITE_IMAGE = '/og.png'

export const SITE_DESCRIPTION =
  'Monitor uptime, SSL certificates, broken links, and cron jobs from around the world. Get alerted in seconds.'

export function absoluteUrl(path = '/') {
  // Absolute URL for a router path, used by <link rel="canonical"> and og:url.
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`
}
