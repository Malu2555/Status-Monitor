<script setup>
// Dashboard overview: one-shot aggregate across all monitors (image-1 style).
import { computed, onMounted, ref } from 'vue'
import * as monitorsApi from '../api/monitors'
import AppIcon from '../components/AppIcon.vue'
import { formatUptime, timeAgo } from '../utils/format'

const data = ref(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await monitorsApi.getOverview()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const checks = computed(() => data.value?.checks || [])
const down = computed(() => data.value?.monitors_down || 0)
const overallStatus = computed(() => {
  if (!data.value || data.value.monitors_total === 0) return 'unknown'
  return down.value > 0 ? 'down' : 'up'
})
const bars = computed(() =>
  checks.value.map((c) => {
    const u = c.uptime_24h
    if (u == null) return 'empty'
    if (u >= 99) return 'up'
    if (u >= 90) return 'warn'
    return 'down'
  }),
)

function latest(list) {
  const ts = list
    .map((c) => c.last_checked_at)
    .filter(Boolean)
    .map((t) => new Date(t).getTime())
  return ts.length ? timeAgo(new Date(Math.max(...ts)).toISOString()) : '—'
}
function lastCheckedFor(label) {
  const c = checks.value
  if (label === 'Uptime') return latest(c)
  if (label === 'SSL & Domain') return latest(c.filter((x) => ['http', 'keyword', 'domain'].includes(x.kind)))
  if (label === 'Broken Links') return latest(c.filter((x) => x.kind === 'broken_links'))
  if (label === 'Scheduled Cron Jobs') return latest(c.filter((x) => x.kind === 'heartbeat'))
  return '—'
}

const concernRows = computed(() => {
  const c = checks.value
  const rows = []
  if (data.value && data.value.monitors_total > 0) {
    rows.push({
      label: 'Uptime',
      icon: 'activity',
      status: down.value > 0 ? 'down' : 'up',
      detail: `${data.value.monitors_up} of ${data.value.monitors_total} monitors up`,
    })
  }
  const days = c.map((x) => x.ssl_days_remaining).filter((v) => v != null)
  if (days.length) {
    const min = Math.min(...days)
    rows.push({
      label: 'SSL & Domain',
      icon: 'lock',
      status: min <= 7 ? 'down' : min <= 30 ? 'warn' : 'up',
      detail: `Active, ${min}d left`,
    })
  }
  const broken = c.filter((x) => x.kind === 'broken_links')
  if (broken.length) {
    const total = broken.reduce((a, x) => a + (x.broken_links || 0), 0)
    rows.push({
      label: 'Broken Links',
      icon: 'link',
      status: total ? 'warn' : 'up',
      detail: `${total} issue${total === 1 ? '' : 's'}`,
    })
  }
  const cron = c.filter((x) => x.kind === 'heartbeat')
  if (cron.length) {
    const late = cron.filter((x) => x.cron_late).length
    rows.push({
      label: 'Scheduled Cron Jobs',
      icon: 'calendar',
      status: late ? 'warn' : 'up',
      detail: late ? `${late} late` : 'Healthy',
    })
  }
  return rows
})

onMounted(load)
</script>

<template>
  <div class="container">
    <div class="flex justify-between items-end flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold">Overview</h1>
        <p class="text-sm text-muted mt-1">A live snapshot across all your monitors.</p>
      </div>
      <router-link :to="{ name: 'monitors' }" class="btn btn-primary">+ Add monitor</router-link>
    </div>

    <div v-if="error" class="error-box mt-4">{{ error }}</div>
    <div v-if="loading" class="empty-state mt-6">Loading overview…</div>

    <template v-else-if="data">
      <div class="overview-grid mt-4">
        <article class="monitor-card overview-status">
          <div class="flex items-center gap-3">
            <span class="overview-status__icon" :class="'is-' + overallStatus">
              <AppIcon :name="overallStatus === 'down' ? 'x' : 'check-circle'" :size="22" />
            </span>
            <div>
              <p class="text-xs text-muted">Current Status</p>
              <p class="text-lg font-semibold">
                {{
                  data.monitors_total === 0
                    ? 'No monitors yet'
                    : overallStatus === 'up'
                      ? 'All systems operational'
                      : 'Some systems are down'
                }}
              </p>
            </div>
          </div>
          <p v-if="data.monitors_total === 0" class="text-sm text-muted mt-3">
            Add a monitor to start seeing uptime, SSL and broken-link state here.
          </p>
        </article>

        <article class="monitor-card">
          <div class="flex justify-between items-center">
            <p class="text-xs text-muted">Overall Uptime (24h)</p>
            <strong class="text-xl">{{ formatUptime(data.overall_uptime_24h) }}</strong>
          </div>
          <div class="uptime-bars mt-3" style="height: 28px">
            <span v-for="(tone, i) in bars" :key="i" class="uptime-bars__bar" :class="'is-' + tone"></span>
          </div>
          <p class="text-xs text-muted mt-2">
            {{ data.monitors_up }} up · {{ data.monitors_down }} down · {{ data.monitors_unknown }} pending
          </p>
        </article>
      </div>

      <div class="active-checks mt-4">
        <div class="monitors-head-row active-checks__head">
          <span>Active Checks</span>
          <span>Status</span>
          <span class="text-right">Last checked</span>
        </div>
        <div v-if="concernRows.length === 0" class="active-checks__empty">
          No active checks yet — add a monitor to populate this table.
        </div>
        <div v-for="row in concernRows" :key="row.label" class="active-checks__row">
          <div class="flex items-center gap-3">
            <span class="status-dot" :class="'dot-' + row.status"></span>
            <span class="font-semibold">{{ row.label }}</span>
          </div>
          <div class="text-sm text-muted">{{ row.detail }}</div>
          <div class="text-xs text-muted text-right">{{ lastCheckedFor(row.label) }}</div>
        </div>
      </div>
    </template>
  </div>
</template>
