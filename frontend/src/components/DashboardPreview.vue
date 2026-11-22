<script setup>
// Decorative dashboard preview for the marketing hero. Static demo data only —
// the real, live product lives at /dashboard after sign-in.
import AppIcon from './AppIcon.vue'
import AppLogo from './AppLogo.vue'

const navItems = [
  { label: 'Home', icon: 'home', active: true },
  { label: 'Monitors', icon: 'monitor' },
  { label: 'Status Pages', icon: 'window' },
  { label: 'Settings', icon: 'settings' },
]

const checks = [
  { name: 'Uptime', target: 'HTTP/Ping', time: '12 minutes ago' },
  { name: 'SSL Certificates', target: 'Active, 84d', time: '12 minutes ago' },
  { name: 'Broken Links', target: '0 issues', time: '13 minutes ago' },
  { name: 'Cron Jobs', target: 'Healthy', time: '11 minutes ago' },
]

const overallBars = [1, 1, 1, 1, 1, 0.55, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0.55, 1, 1, 1, 1, 1, 1]
const historyBars = Array.from({ length: 44 }, (_, index) => (index === 13 || index === 30 ? 0.5 : 1))

const responsePath =
  'M4 58 L12 54 L20 60 L28 49 L36 53 L44 44 L52 47 L60 38 L68 41 L76 31 L84 36 L92 28 L100 33 L108 22 L116 27 L124 20 L132 30 L140 18 L148 24 L156 15 L164 22 L172 12 L180 20 L188 9 L196 16 L204 26 L212 17 L220 24 L228 13 L236 19 L244 10 L252 18 L260 12 L268 21 L276 16 L284 24 L292 19 L300 27 L308 20 L316 26'
const responseArea = `${responsePath} L316 72 L4 72 Z`
const chartLabels = ['08 Jan', '10 Jan', '15 Jan', '20 Jan', '27 Jan', '31 Jan']
</script>

<template>
  <div class="preview-wrap" role="img" aria-label="Preview of the Status Monitor dashboard showing system status, uptime history, response times and active checks">
    <div class="preview">
      <aside class="preview-sidebar">
        <div class="preview-brand">
          <AppLogo :size="22" />
          <span>Status Monitor</span>
        </div>
        <nav class="preview-nav" aria-hidden="true">
          <div
            v-for="item in navItems"
            :key="item.label"
            class="preview-nav-item"
            :class="{ 'is-active': item.active }"
          >
            <AppIcon :name="item.icon" :size="14" />
            <span>{{ item.label }}</span>
          </div>
        </nav>
        <div class="preview-sidebar-footer">
          <div class="preview-nav-item">
            <AppIcon name="settings" :size="14" />
            <span>Settings</span>
          </div>
        </div>
      </aside>

      <section class="preview-main">
        <header class="preview-topbar">
          <span>Status Monitor</span>
          <span class="preview-topbar-icons">
            <AppIcon name="refresh" :size="13" />
            <span class="preview-avatar"><AppIcon name="user" :size="12" /></span>
          </span>
        </header>

        <div class="preview-body">
          <div class="preview-row">
            <article class="preview-card preview-status-card">
              <span class="preview-check"><AppIcon name="check-circle" :size="26" /></span>
              <div>
                <p class="preview-muted">Current Status:</p>
                <p class="preview-strong">All Status Monitor Systems</p>
              </div>
            </article>

            <article class="preview-card">
              <div class="preview-card-head">
                <span class="preview-muted">Overall Uptime:</span>
                <span class="preview-strong">99.98%</span>
              </div>
              <div class="bar-strip bar-strip--small" aria-hidden="true">
                <span v-for="(bar, index) in overallBars" :key="index" :class="{ 'is-soft': bar < 1 }"></span>
              </div>
              <div class="preview-axis">
                <span>15-Dec</span>
                <span>5th Dec</span>
                <span>16-Dec</span>
                <span class="preview-axis-right"><b class="is-up">100%</b><b>0%</b></span>
              </div>
            </article>
          </div>

          <div class="preview-row">
            <article class="preview-card">
              <div class="preview-card-head">
                <span class="preview-strong">Uptime History</span>
                <span class="preview-muted">100%</span>
              </div>
              <div class="bar-strip bar-strip--history" aria-hidden="true">
                <span v-for="(bar, index) in historyBars" :key="index" :class="{ 'is-soft': bar < 1 }"></span>
              </div>
              <div class="preview-axis">
                <span>16-Dec</span>
                <span>20-Dec</span>
                <span>24-Dec</span>
                <span>28-Dec</span>
              </div>
            </article>

            <article class="preview-card preview-chart-card">
              <div class="preview-card-head">
                <span class="preview-strong">Multi-location Response Time</span>
                <span class="preview-legend"><i></i> Response Time</span>
              </div>
              <div class="preview-chart">
                <svg viewBox="0 0 320 76" preserveAspectRatio="none" aria-hidden="true">
                  <defs>
                    <linearGradient id="sm-response-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="var(--preview-chart-line)" stop-opacity=".26" />
                      <stop offset="100%" stop-color="var(--preview-chart-line)" stop-opacity="0" />
                    </linearGradient>
                  </defs>
                  <path :d="responseArea" fill="url(#sm-response-fill)" />
                  <path :d="responsePath" fill="none" stroke="var(--preview-chart-line)" stroke-width="1.8" stroke-linejoin="round" />
                </svg>
                <div class="preview-chart-ylabels" aria-hidden="true">
                  <span>300</span><span>200</span><span>100</span><span>0</span>
                </div>
              </div>
              <div class="preview-axis preview-axis--chart" aria-hidden="true">
                <span v-for="label in chartLabels" :key="label">{{ label }}</span>
              </div>
            </article>
          </div>

          <article class="preview-card preview-table-card">
            <div class="preview-table-head">
              <span>Active Checks</span>
              <span>Active</span>
              <span></span>
            </div>
            <div v-for="row in checks" :key="row.name" class="preview-table-row">
              <span class="preview-check-name">
                <AppIcon name="check-circle" :size="14" class="preview-up-icon" />
                {{ row.name }}
              </span>
              <span class="preview-check-value">{{ row.target }}</span>
              <span class="preview-check-time">{{ row.time }}</span>
              <AppIcon name="kebab" :size="14" class="preview-kebab" />
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>
