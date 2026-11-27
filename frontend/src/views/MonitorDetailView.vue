<script setup>
// Monitor detail mini-page: sidebar of concern-specific views for one monitor.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as maintenanceApi from '../api/maintenance'
import * as monitorsApi from '../api/monitors'
import AppIcon from '../components/AppIcon.vue'
import IncidentTimeline from '../components/IncidentTimeline.vue'
import MonitorForm from '../components/MonitorForm.vue'
import Sparkline from '../components/UptimeSparkline.vue'
import StatusBadge from '../components/StatusBadge.vue'
import UptimeBars from '../components/UptimeBars.vue'
import { formatUptime, kindLabel, timeAgo } from '../utils/format'

const route = useRoute()
const router = useRouter()

const monitor = ref(null)
const loading = ref(true)
const error = ref('')
const busy = ref(false)
const stats7 = ref(null)
const stats14 = ref(null)
const stats30 = ref(null)
const regions = ref([])
const ssl = ref(null)
const domain = ref(null)
const crawl = ref(null)
const windows = ref([])
const range = ref(24)
const buckets = ref([])

const monitorId = computed(() => Number(route.params.id))
const tab = computed(() => route.params.tab || 'overview')
const kind = computed(() => monitor.value?.kind || 'http')
const isHttp = computed(() => ['http', 'keyword'].includes(kind.value))

const sidebar = computed(() => {
  const items = [
    { key: 'overview', label: 'Overview', icon: 'home' },
    { key: 'uptime', label: 'Uptime', icon: 'activity' },
  ]
  if (isHttp.value) items.push({ key: 'certificate-health', label: 'Certificate health', icon: 'lock' })
  if (kind.value === 'broken_links') items.push({ key: 'broken-links', label: 'Broken links', icon: 'link' })
  if (kind.value === 'domain') items.push({ key: 'domain', label: 'Domain', icon: 'calendar' })
  items.push({ key: 'incidents', label: 'Incidents', icon: 'bell' })
  items.push({ key: 'maintenance', label: 'Maintenance', icon: 'calendar' })
  items.push({ key: 'settings', label: 'Settings', icon: 'settings' })
  return items
})

const bucketValues = computed(() => buckets.value.map((b) => b.response_avg_ms))
const bucketStats = computed(() => {
  const ms = buckets.value.map((b) => b.response_avg_ms).filter((v) => v != null)
  if (!ms.length) return null
  const sum = ms.reduce((a, b) => a + b, 0)
  return { high: Math.max(...ms), low: Math.min(...ms), avg: Math.round(sum / ms.length) }
})

function go(key) {
  if (key === 'overview') router.push({ name: 'monitor', params: { id: monitorId.value } })
  else router.push({ name: 'monitor', params: { id: monitorId.value, tab: key } })
}

async function loadBuckets() {
  try {
    buckets.value = await monitorsApi.uptimeBuckets(
      monitorId.value,
      range.value,
      range.value >= 168 ? 6 : 1,
    )
  } catch {
    buckets.value = []
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    monitor.value = await monitorsApi.getMonitor(monitorId.value)
  } catch (e) {
    error.value = e.message
    loading.value = false
    return
  }
  const results = await Promise.allSettled([
    monitorsApi.monitorStats(monitorId.value, 168),
    monitorsApi.monitorStats(monitorId.value, 336),
    monitorsApi.monitorStats(monitorId.value, 720),
    monitorsApi.monitorRegions(monitorId.value, 24),
  ])
  stats7.value = results[0].status === 'fulfilled' ? results[0].value : null
  stats14.value = results[1].status === 'fulfilled' ? results[1].value : null
  stats30.value = results[2].status === 'fulfilled' ? results[2].value : null
  regions.value = results[3].status === 'fulfilled' ? results[3].value : []
  if (isHttp.value) {
    try {
      ssl.value = await monitorsApi.monitorSsl(monitorId.value)
    } catch {
      ssl.value = null
    }
  }
  if (kind.value === 'domain') {
    try {
      domain.value = await monitorsApi.monitorDomain(monitorId.value)
    } catch {
      domain.value = null
    }
  }
  if (kind.value === 'broken_links') {
    try {
      crawl.value = await monitorsApi.monitorCrawl(monitorId.value)
    } catch {
      crawl.value = null
    }
  }
  loading.value = false
  loadBuckets()
}

async function loadWindows() {
  try {
    windows.value = await maintenanceApi.listWindows(monitorId.value)
  } catch {
    windows.value = []
  }
}

async function crawlNow() {
  busy.value = true
  try {
    crawl.value = await monitorsApi.runCrawl(monitorId.value)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function save(payload) {
  busy.value = true
  try {
    await monitorsApi.updateMonitor(monitorId.value, payload)
    await load()
    go('overview')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function removeMonitor() {
  if (!window.confirm(`Delete "${monitor.value.name}" and its check history?`)) return
  try {
    await monitorsApi.deleteMonitor(monitorId.value)
    router.push({ name: 'dashboard' })
  } catch (e) {
    error.value = e.message
  }
}

watch(monitorId, load, { immediate: true })
watch(tab, (t) => {
  if (t === 'uptime') loadBuckets()
  if (t === 'maintenance') loadWindows()
})
watch(range, loadBuckets)
</script>

<template>
  <div class="container">
    <router-link :to="{ name: 'dashboard' }" class="text-sm text-muted">← Back to monitors</router-link>

    <div v-if="loading" class="empty-state mt-6">Loading monitor…</div>
    <div v-else-if="error && !monitor" class="error-box mt-6">{{ error }}</div>

    <template v-else-if="monitor">
      <div class="monitor-header">
        <div class="flex items-center gap-3">
          <span class="status-dot" :class="'dot-' + monitor.last_status"></span>
          <div>
            <h1 class="text-2xl font-bold">{{ monitor.name }}</h1>
            <p class="text-xs text-muted">
              {{ kindLabel(monitor.kind) }}
              <template v-if="monitor.url">
                · <a :href="monitor.url" target="_blank" rel="noopener">{{ monitor.url }}</a>
              </template>
            </p>
          </div>
        </div>
        <StatusBadge :status="monitor.last_status" />
      </div>

      <div v-if="error" class="error-box mt-4">{{ error }}</div>

      <div class="monitor-layout">
        <aside class="monitor-sidebar">
          <button
            v-for="item in sidebar"
            :key="item.key"
            type="button"
            class="monitor-nav-item"
            :class="{ 'is-active': tab === item.key }"
            @click="go(item.key)"
          >
            <AppIcon :name="item.icon" :size="18" />
            <span>{{ item.label }}</span>
          </button>
        </aside>

        <section class="monitor-content">
          <div v-if="tab === 'overview'" class="monitor-cards">
            <article class="monitor-card">
              <header class="monitor-card__head">
                <span class="status-dot" :class="'dot-' + monitor.last_status"></span><h2>Uptime</h2>
              </header>
              <p class="text-sm text-muted">
                {{ monitor.name }} is {{ monitor.last_status }}. Last checked
                {{ timeAgo(monitor.last_checked_at) }}.
              </p>
              <div class="stat-row">
                <div class="stat-cell"><span>Past 7 days</span><strong>{{ formatUptime(stats7?.uptime_percent) }}</strong></div>
                <div class="stat-cell"><span>Past 14 days</span><strong>{{ formatUptime(stats14?.uptime_percent) }}</strong></div>
                <div class="stat-cell"><span>Past 30 days</span><strong>{{ formatUptime(stats30?.uptime_percent) }}</strong></div>
              </div>
            </article>

            <article v-if="isHttp" class="monitor-card">
              <header class="monitor-card__head">
                <span class="status-dot" :class="ssl && ssl.error ? 'dot-down' : 'dot-up'"></span><h2>Certificate health</h2>
              </header>
              <p class="text-sm text-muted">
                <template v-if="ssl && ssl.days_remaining != null">Certificate is healthy. Expires in {{ ssl.days_remaining }} day(s).</template>
                <template v-else-if="ssl && ssl.error">TLS: {{ ssl.error }}</template>
                <template v-else>Not checked yet — run manage.py check_ssl.</template>
              </p>
              <div v-if="ssl && ssl.not_after" class="expiry-box">
                <span>Expires in</span><strong>{{ ssl.days_remaining }} day(s)</strong>
              </div>
            </article>

            <article v-if="kind === 'broken_links'" class="monitor-card">
              <header class="monitor-card__head">
                <span class="status-dot" :class="crawl && crawl.broken_links.length ? 'dot-down' : 'dot-up'"></span><h2>Broken links</h2>
              </header>
              <p class="text-sm text-muted">
                <template v-if="crawl && crawl.run">Last crawl {{ timeAgo(crawl.run.started_at) }} · {{ crawl.run.pages_crawled }} page(s).</template>
                <template v-else>No crawl yet.</template>
              </p>
              <div class="stat-row">
                <div class="stat-cell"><span>Broken links</span><strong>{{ (crawl && crawl.broken_links.length) || 0 }}</strong></div>
                <div class="stat-cell"><span>URLs crawled</span><strong>{{ (crawl && crawl.run && crawl.run.links_checked) || 0 }}</strong></div>
              </div>
            </article>

            <article v-if="kind === 'domain'" class="monitor-card">
              <header class="monitor-card__head"><span class="status-dot dot-up"></span><h2>Domain</h2></header>
              <p v-if="domain" class="text-sm text-muted">
                Expires {{ domain.expires_at ? new Date(domain.expires_at).toLocaleDateString() : '—' }}
                ({{ domain.days_remaining ?? '—' }} day(s) left).
              </p>
              <p v-else class="text-sm text-muted">No domain data yet.</p>
            </article>

            <article v-if="regions.length" class="monitor-card">
              <header class="monitor-card__head"><span class="status-dot dot-up"></span><h2>Regions</h2></header>
              <ul class="text-sm">
                <li v-for="r in regions" :key="r.region" class="flex justify-between">
                  <span>{{ r.region }}</span>
                  <span :class="r.last_status === 'up' ? 'text-up' : 'text-down'">{{ r.last_status }} · {{ formatUptime(r.uptime_percent) }}</span>
                </li>
              </ul>
            </article>
          </div>
          <div v-else-if="tab === 'uptime'">
            <div class="flex justify-between items-center flex-wrap gap-3">
              <h2 class="text-lg font-semibold">Uptime</h2>
              <select v-model.number="range" class="select" style="max-width: 200px">
                <option :value="24">Last 24 hours</option>
                <option :value="168">Last 7 days</option>
                <option :value="336">Last 14 days</option>
                <option :value="720">Last 30 days</option>
              </select>
            </div>

            <div class="monitor-alert" :class="monitor.last_status === 'down' ? 'is-down' : 'is-up'">
              <AppIcon :name="monitor.last_status === 'down' ? 'x' : 'check-circle'" :size="20" />
              <div>
                <p class="font-semibold">{{ monitor.last_status === 'down' ? 'Down' : 'All good!' }}</p>
                <p class="text-sm text-muted">
                  {{ monitor.last_status === 'down' ? 'The latest check failed.' : 'We were able to verify that ' + monitor.name + ' is online.' }}
                </p>
              </div>
            </div>

            <div v-if="bucketStats" class="stat-row mt-4">
              <div class="stat-cell"><span>Highest</span><strong>{{ bucketStats.high }} ms</strong></div>
              <div class="stat-cell"><span>Lowest</span><strong>{{ bucketStats.low }} ms</strong></div>
              <div class="stat-cell"><span>Average</span><strong>{{ bucketStats.avg }} ms</strong></div>
            </div>

            <div class="mt-4">
              <Sparkline :values="bucketValues" :height="140" />
            </div>
            <div class="mt-3">
              <UptimeBars :buckets="buckets" />
            </div>
            <p v-if="regions.length" class="text-xs text-muted mt-3">
              Monitored from:
              <span v-for="r in regions" :key="r.region">{{ r.region }} </span>
            </p>
          </div>

          <div v-else-if="tab === 'certificate-health'">
            <h2 class="text-lg font-semibold">Certificate health</h2>
            <div v-if="ssl" class="card mt-3">
              <p class="text-sm">Issuer: <strong>{{ ssl.issuer || '—' }}</strong></p>
              <p class="text-sm mt-1">Subject: {{ ssl.subject || '—' }}</p>
              <p class="text-sm mt-1">Not after: {{ ssl.not_after ? new Date(ssl.not_after).toLocaleString() : '—' }}</p>
              <p class="text-sm mt-1">
                Days remaining:
                <strong :class="ssl.days_remaining != null && ssl.days_remaining <= 30 ? 'text-warn' : 'text-up'">{{ ssl.days_remaining ?? '—' }}</strong>
              </p>
              <p v-if="ssl.error" class="text-xs text-down mt-2">{{ ssl.error }}</p>
            </div>
            <p v-else class="text-sm text-muted mt-3">No certificate data yet.</p>
          </div>

          <div v-else-if="tab === 'broken-links'">
            <div class="flex justify-between items-center flex-wrap gap-2">
              <h2 class="text-lg font-semibold">Broken links</h2>
              <button class="btn btn-ghost btn-sm" :disabled="busy" @click="crawlNow">{{ busy ? 'Crawling…' : 'Run crawl now' }}</button>
            </div>
            <p v-if="crawl && crawl.run" class="text-xs text-muted mt-1">
              Last crawl {{ timeAgo(crawl.run.started_at) }} · {{ crawl.run.pages_crawled }} page(s) · {{ crawl.run.links_checked }} link(s) checked
            </p>
            <p v-else class="text-xs text-muted mt-1">No crawl yet.</p>

            <div v-if="crawl && crawl.broken_links.length" class="card mt-3 overflow-x-auto">
              <table class="text-xs w-full crawl-table">
                <thead class="text-muted">
                  <tr>
                    <th class="text-left py-1">Target</th>
                    <th class="text-left py-1">Found on</th>
                    <th class="text-left py-1">Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="link in crawl.broken_links" :key="link.id" class="border-t">
                    <td class="py-1 truncate" style="max-width: 280px">{{ link.target_url }}</td>
                    <td class="py-1 truncate text-muted" style="max-width: 220px">{{ link.source_url }}</td>
                    <td class="py-1">{{ link.status_code || link.error }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="text-sm text-muted mt-3">No open broken links.</p>
          </div>
          <div v-else-if="tab === 'domain'">
            <h2 class="text-lg font-semibold">Domain</h2>
            <div v-if="domain" class="card mt-3">
              <p class="text-sm">{{ domain.domain }}</p>
              <p class="text-sm mt-1">Status: <strong>{{ domain.status || 'unknown' }}</strong></p>
              <p class="text-sm mt-1">Registrar: {{ domain.registrar || '—' }}</p>
              <p class="text-sm mt-1">Expires: {{ domain.expires_at ? new Date(domain.expires_at).toLocaleDateString() : '—' }} ({{ domain.days_remaining ?? '—' }} day(s) left)</p>
              <p v-if="domain.error" class="text-xs text-down mt-2">{{ domain.error }}</p>
            </div>
            <p v-else class="text-sm text-muted mt-3">No domain data yet.</p>
          </div>

          <div v-else-if="tab === 'incidents'">
            <h2 class="text-lg font-semibold">Incidents</h2>
            <IncidentTimeline :monitor-id="monitor.id" />
          </div>

          <div v-else-if="tab === 'maintenance'">
            <div class="flex justify-between items-center flex-wrap gap-2">
              <h2 class="text-lg font-semibold">Maintenance windows</h2>
              <router-link :to="{ name: 'maintenance' }" class="btn btn-ghost btn-sm">Manage</router-link>
            </div>
            <div v-if="windows.length" class="card mt-3 text-sm">
              <div v-for="w in windows" :key="w.id" class="py-2 border-t">
                {{ new Date(w.starts_at).toLocaleString() }} → {{ new Date(w.ends_at).toLocaleString() }}
                <span v-if="w.note" class="text-muted"> · {{ w.note }}</span>
              </div>
            </div>
            <p v-else class="text-sm text-muted mt-3">No maintenance windows scheduled.</p>
          </div>

          <div v-else-if="tab === 'settings'">
            <div class="flex justify-between items-center flex-wrap gap-2">
              <h2 class="text-lg font-semibold">Settings</h2>
              <button class="btn btn-danger btn-sm" @click="removeMonitor">Delete monitor</button>
            </div>
            <MonitorForm class="mt-3" :monitor="monitor" @save="save" @cancel="go('overview')" :busy="busy" />
          </div>

          <div v-else class="text-sm text-muted">Unknown tab.</div>
        </section>
      </div>
    </template>
  </div>
</template>
