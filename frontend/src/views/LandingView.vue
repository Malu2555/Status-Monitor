<script setup>
// Marketing landing page: hero, product preview, features, status page sample, pricing.
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppIcon from '../components/AppIcon.vue'
import DashboardPreview from '../components/DashboardPreview.vue'

const router = useRouter()
const auth = useAuthStore()
const website = ref('')
const urlError = ref('')

const features = [
  {
    title: 'HTTP & Keyword Monitoring',
    description: 'Continuous checks from multiple regions, plus keyword assertions that catch broken pages.',
    icon: 'activity',
    tone: 'green',
  },
  {
    title: 'SSL & Domain Expiry',
    description: 'Get notified before certificates and domains expire.',
    icon: 'lock',
    tone: 'amber',
  },
  {
    title: 'Broken Links Crawler',
    description: 'Scan your site automatically to find and fix broken links.',
    icon: 'link',
    tone: 'pink',
  },
  {
    title: 'Scheduled Cron Jobs',
    description: 'Ensure your background jobs and crons run on time.',
    icon: 'calendar',
    tone: 'purple',
  },
  {
    title: 'Public Status Pages',
    description: 'Build beautiful, custom status pages for your users.',
    icon: 'window',
    tone: 'blue',
  },
  {
    title: 'Instant Alerts',
    description: 'Email, Slack, Discord, Telegram and webhooks when downtime occurs.',
    icon: 'bell',
    tone: 'orange',
    id: 'integrations',
  },
]

const plans = [
  {
    name: 'Free',
    price: '$0',
    features: ['1 monitor', '5 min intervals', 'Public status page', 'Email alerts'],
    cta: 'Create free account',
    featured: false,
    query: {},
  },
  {
    name: 'Pro',
    price: '$9',
    features: ['10 monitors', '1 min intervals', 'Custom status pages', 'SSL & domain monitoring'],
    cta: 'Start with Pro',
    featured: true,
    badge: 'Most Popular',
    query: { plan: 'pro' },
  },
  {
    name: 'Business',
    price: '$29',
    features: ['50 monitors', '1 min intervals', 'Multi-region checks', 'Webhook & chat alerts'],
    cta: 'Start with Business',
    featured: false,
    query: { plan: 'business' },
  },
]

const services = [
  { name: 'Homepage', bars: 46 },
  { name: 'API', bars: 44 },
  { name: 'Dashboard', bars: 48 },
]

const useCases = [
  {
    title: 'SaaS & product teams',
    promise: 'Ship without surprises.',
    icon: 'spark',
    tone: 'green',
    bullets: [
      'Keyword checks on signup and checkout flows',
      'Cron heartbeat for background jobs',
      'Public status page for your customers',
    ],
  },
  {
    title: 'DevOps & sysadmins',
    promise: 'Know before your users do.',
    icon: 'monitor',
    tone: 'blue',
    bullets: [
      'Multi-region checks with response times',
      'TLS and domain expiry alerts',
      'API tokens and webhooks into your tooling',
    ],
  },
  {
    title: 'Web & marketing agencies',
    promise: 'Every client, one dashboard.',
    icon: 'link',
    tone: 'pink',
    bullets: [
      'Branded status page per client',
      'Broken-link crawls for SEO hygiene',
      'CSV uptime reports',
    ],
  },
  {
    title: 'E-commerce & shops',
    promise: 'Protect the checkout.',
    icon: 'bell',
    tone: 'orange',
    bullets: [
      '“Add to cart” keyword monitoring',
      'Instant alerts by email, Slack or Discord',
      'SSL and domain expiry warnings',
    ],
  },
]

function normalizeUrl(raw) {
  let value = raw.trim()
  if (!value) return ''
  if (!/^https?:\/\//i.test(value)) value = `https://${value}`
  try {
    const parsed = new URL(value)
    if (!parsed.hostname.includes('.') || parsed.hostname.startsWith('.') || parsed.hostname.endsWith('.')) {
      return ''
    }
    return parsed.toString()
  } catch {
    return ''
  }
}

function startMonitoring() {
  const url = normalizeUrl(website.value)
  if (!url) {
    urlError.value = 'Enter a valid website address, e.g. example.com'
    return
  }
  urlError.value = ''
  const query = { url }
  router.push(auth.isAuthenticated ? { name: 'dashboard', query } : { name: 'register', query })
}

function serviceBars(count, softIndexes = []) {
  return Array.from({ length: count }, (_, index) => (softIndexes.includes(index) ? 'is-soft' : ''))
}
</script>

<template>
  <div class="landing">
    <section class="hero">
      <div class="hero-glow" aria-hidden="true"></div>
      <div class="container hero-inner">
        <h1 class="hero-title">All-in-One Website &amp;<br />Uptime Monitoring</h1>
        <p class="hero-sub">
          Monitor uptime, SSL certificates, broken links, and cron jobs from around the world.
          Get alerted in seconds.
        </p>
        <form class="hero-form" @submit.prevent="startMonitoring">
          <AppIcon name="globe" :size="19" class="hero-form-icon" />
          <label class="sr-only" for="website">Website address</label>
          <input
            id="website"
            v-model="website"
            type="text"
            inputmode="url"
            autocomplete="url"
            placeholder="yourwebsite.com"
            :aria-invalid="Boolean(urlError)"
          />
          <button type="submit" class="btn btn-primary hero-form-btn">Monitor Now</button>
        </form>
        <p v-if="urlError" class="hero-error">{{ urlError }}</p>
        <p class="hero-note">1 monitor free forever · No credit card required</p>
      </div>
    </section>

    <DashboardPreview />

    <section id="features" class="section features-section">
      <div class="container">
        <h2 class="sr-only">Features</h2>
        <div class="features-grid">
          <article
            v-for="feature in features"
            :id="feature.id"
            :key="feature.title"
            class="feature-card"
          >
            <span class="icon-tile" :class="`tone-${feature.tone}`">
              <AppIcon :name="feature.icon" :size="20" />
            </span>
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.description }}</p>
          </article>
        </div>
      </div>
    </section>

    <section id="use-cases" class="section usecases-section">
      <div class="container">
        <div class="section-heading">
          <p class="eyebrow">Use cases</p>
          <h2>Built for teams that can’t afford downtime</h2>
          <p class="section-sub">
            One dashboard for the sites, shops and services you’re responsible for — without
            switching between tools.
          </p>
        </div>
        <div class="usecases-grid">
          <article v-for="useCase in useCases" :key="useCase.title" class="usecase-card">
            <div class="usecase-head">
              <span class="icon-tile" :class="`tone-${useCase.tone}`">
                <AppIcon :name="useCase.icon" :size="20" />
              </span>
              <div>
                <h3>{{ useCase.title }}</h3>
                <p class="usecase-promise">{{ useCase.promise }}</p>
              </div>
            </div>
            <ul class="usecase-list">
              <li v-for="line in useCase.bullets" :key="line">
                <AppIcon name="check" :size="14" class="usecase-check" />
                <span>{{ line }}</span>
              </li>
            </ul>
          </article>
        </div>
      </div>
    </section>

    <section id="status-pages" class="status-band" aria-label="Public status page preview">
      <div class="browser-frame">
        <div class="browser-bar">
          <span class="browser-dots" aria-hidden="true"><i></i><i></i><i></i></span>
          <span class="browser-address">yourwebsite.com</span>
        </div>
        <div class="browser-body">
          <div class="status-banner">
            <AppIcon name="check-circle" :size="18" />
            <span>All Status Monitor Systems Operational</span>
            <span class="status-badge">100% uptime</span>
          </div>
          <p class="status-heading">Uptime History</p>
          <div class="service-row" v-for="service in services" :key="service.name">
            <span class="service-name">{{ service.name }}</span>
            <span class="service-bars" aria-hidden="true">
              <span
                v-for="(tone, index) in serviceBars(service.bars, [17, 39])"
                :key="index"
                :class="tone"
              ></span>
            </span>
          </div>
        </div>
      </div>
    </section>

    <section id="pricing" class="section pricing-section">
      <div class="container">
        <h2 class="sr-only">Pricing</h2>
        <div class="pricing-grid">
          <article
            v-for="plan in plans"
            :key="plan.name"
            class="pricing-card"
            :class="{ 'is-featured': plan.featured }"
          >
            <span v-if="plan.badge" class="pricing-badge">{{ plan.badge }}</span>
            <h3 class="pricing-name">{{ plan.name }}</h3>
            <p class="pricing-price">
              {{ plan.price }}<small>/mo</small>
            </p>
            <ul class="pricing-list">
              <li v-for="line in plan.features" :key="line">{{ line }}</li>
            </ul>
            <router-link
              :to="{ name: auth.isAuthenticated ? 'dashboard' : 'register', query: plan.query }"
              class="btn pricing-cta"
              :class="plan.featured ? 'btn-primary' : 'btn-ghost'"
            >
              {{ auth.isAuthenticated ? 'Go to dashboard' : plan.cta }}
            </router-link>
          </article>
        </div>
      </div>
    </section>

    <div v-if="!auth.isAuthenticated" class="mobile-cta">
      <router-link :to="{ name: 'register' }" class="btn btn-primary">
        Start Monitoring Free
      </router-link>
    </div>
  </div>
</template>
