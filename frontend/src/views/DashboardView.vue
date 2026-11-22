<script setup>
// Private dashboard: monitor CRUD + uptime chart + plan usage/billing.
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import * as monitorsApi from '../api/monitors'
import IncidentTimeline from '../components/IncidentTimeline.vue'
import MonitorCard from '../components/MonitorCard.vue'
import MonitorForm from '../components/MonitorForm.vue'
import UptimeChart from '../components/UptimeChart.vue'
import UpgradeCard from '../components/UpgradeCard.vue'
import { useAuthStore } from '../stores/auth'
import { formatMs, kindLabel, statusLabel, timeAgo } from '../utils/format'
import { logger } from '../utils/logger'

const auth = useAuthStore()
const route = useRoute()

const monitors = ref([])
const loading = ref(true)
const error = ref('')
const showForm = ref(false)
const editing = ref(null)
const detail = ref(null) // { monitor, stats }
const busy = ref(false)
const createdHeartbeat = ref(null)
const prefillUrl = ref(typeof route.query.url === 'string' ? route.query.url : '')
const prefillConsumed = ref(false)

const heartbeatPingUrl = computed(() =>
  createdHeartbeat.value?.heartbeat_token
    ? `${window.location.origin}/api/public/heartbeat/${createdHeartbeat.value.heartbeat_token}`
    : '',
)

async function copyHeartbeat() {
  try {
    await navigator.clipboard.writeText(heartbeatPingUrl.value)
  } catch {
    /* clipboard unavailable — the input is selectable */
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    monitors.value = await monitorsApi.listMonitors()
    await auth.refreshBilling()
    if (prefillUrl.value && !prefillConsumed.value) {
      prefillConsumed.value = true
      editing.value = null
      showForm.value = true
    }
  } catch (e) {
    error.value = e.message
    logger.error('dashboard load failed', e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  prefillUrl.value = ''
  showForm.value = true
  error.value = ''
}

function openEdit(monitor) {
  editing.value = monitor
  showForm.value = true
  error.value = ''
}

async function handleSave(payload) {
  busy.value = true
  error.value = ''
  try {
    if (editing.value) {
      await monitorsApi.updateMonitor(editing.value.id, payload)
    } else {
      const created = await monitorsApi.createMonitor(payload)
      if (created.kind === 'heartbeat') createdHeartbeat.value = created
    }
    showForm.value = false
    editing.value = null
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function handleDelete(monitor) {
  if (!window.confirm(`Delete "${monitor.name}" and its check history?`)) return
  try {
    await monitorsApi.deleteMonitor(monitor.id)
    if (detail.value?.monitor.id === monitor.id) detail.value = null
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function toggleDetail(monitor) {
  if (detail.value?.monitor.id === monitor.id) {
    detail.value = null
    return
  }
  try {
    const [stats, regions] = await Promise.all([
      monitorsApi.monitorStats(monitor.id, 24),
      monitorsApi.monitorRegions(monitor.id, 24),
    ])
    const extra = {}
    if (['http', 'keyword'].includes(monitor.kind)) {
      extra.ssl = await monitorsApi.monitorSsl(monitor.id)
    } else if (monitor.kind === 'domain') {
      extra.domain = await monitorsApi.monitorDomain(monitor.id)
    } else if (monitor.kind === 'broken_links') {
      extra.crawl = await monitorsApi.monitorCrawl(monitor.id)
    }
    detail.value = { monitor, stats, regions, ...extra }
  } catch (e) {
    error.value = e.message
  }
}

async function crawlNow() {
  if (!detail.value) return
  busy.value = true
  try {
    detail.value.crawl = await monitorsApi.runCrawl(detail.value.monitor.id)
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="container">
    <div class="flex justify-between items-center flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold">Dashboard</h1>
        <p class="text-sm text-muted mt-1">
          Welcome back, {{ auth.user?.username }} — manage your monitored sites.
        </p>
      </div>
      <button class="btn btn-primary" @click="openCreate" :disabled="monitors.length >= (auth.user?.monitors_limit ?? 1)">
        + Add monitor
      </button>
    </div>

    <div class="mt-6">
      <UpgradeCard v-if="auth.user" :summary="auth.user" />
    </div>

    <div v-if="createdHeartbeat" class="card bg-primary-soft mt-4 text-sm">
      <p class="font-medium">
        {{ createdHeartbeat.name }} is ready — ping this URL from your cron job:
      </p>
      <input class="input mt-2" :value="heartbeatPingUrl" readonly />
      <div class="flex gap-2 mt-2">
        <button class="btn btn-ghost btn-sm" @click="copyHeartbeat">Copy ping URL</button>
        <button class="btn btn-ghost btn-sm" @click="createdHeartbeat = null">Dismiss</button>
      </div>
    </div>

    <p class="text-sm mt-3">
      <router-link :to="{ name: 'statuspages' }" class="text-primary">Manage status pages →</router-link>
    </p>

    <div v-if="error" class="error-box mt-6">{{ error }}</div>

    <MonitorForm
      v-if="showForm"
      class="mt-6"
      :monitor="editing"
      :initial-url="editing ? '' : prefillUrl"
      @save="handleSave"
      @cancel="showForm = false"
      :busy="busy"
    />

    <div v-if="loading" class="empty-state mt-6">Loading your monitors…</div>

    <div v-else-if="monitors.length === 0 && !showForm" class="empty-state mt-6">
      <p class="font-medium">You have no monitors yet</p>
      <p class="text-sm mt-1">Add your first website to start tracking its uptime.</p>
    </div>

    <div v-else class="monitor-grid mt-6">
      <MonitorCard
        v-for="m in monitors"
        :key="m.id"
        :monitor="m"
        show-actions
        @select="toggleDetail(m)"
        @edit="openEdit"
        @delete="handleDelete"
      />
    </div>

    <div v-if="detail" class="mt-6">
      <div class="panel">
        <div class="flex justify-between items-center flex-wrap gap-3 mb-4">
          <div>
            <h2 class="text-lg font-semibold">
              {{ detail.monitor.name }}
              <span class="text-xs font-normal text-muted">· {{ kindLabel(detail.monitor.kind) }}</span>
            </h2>
            <p class="text-xs text-muted mt-1">
              {{ statusLabel(detail.monitor.last_status) }} · last checked
              {{ timeAgo(detail.monitor.last_checked_at) }}
              <template v-if="['http', 'keyword'].includes(detail.monitor.kind)">
                · response {{ formatMs(detail.monitor.last_response_ms) }}
              </template>
            </p>
          </div>
          <span class="text-sm font-semibold text-up">
            {{ detail.stats.uptime_percent != null ? detail.stats.uptime_percent + '% uptime (24h)' : 'no data yet' }}
          </span>
        </div>
        <UptimeChart v-if="detail.stats.series.length" :series="detail.stats.series" :height="160" />
        <p v-else class="text-sm text-muted">No checks recorded yet — they appear after the first scheduled run.</p>

        <div v-if="detail.regions && detail.regions.length" class="mt-4">
          <p class="text-xs font-semibold text-muted mb-2">REGIONS (consensus)</p>
          <div class="flex flex-wrap gap-3 text-xs">
            <span v-for="r in detail.regions" :key="r.region">
              <strong>{{ r.region }}</strong>:
              <span :class="r.last_status === 'up' ? 'text-up' : 'text-down'">{{ r.last_status }}</span>
              · {{ r.uptime_percent != null ? r.uptime_percent + '%' : '—' }}
            </span>
          </div>
        </div>

        <p v-if="detail.ssl" class="text-xs text-muted mt-3">
          TLS:
          <template v-if="detail.ssl.days_remaining != null">
            {{ detail.ssl.days_remaining }} day(s) left
            <template v-if="detail.ssl.issuer"> · {{ detail.ssl.issuer }}</template>
          </template>
          <template v-else>{{ detail.ssl.error }}</template>
        </p>

        <div v-if="detail.domain" class="card mt-4 text-sm">
          <div class="flex justify-between items-start flex-wrap gap-3">
            <div>
              <p class="text-xs font-semibold text-muted">DOMAIN EXPIRY</p>
              <p class="mt-1">
                <strong>{{ detail.domain.domain }}</strong>
                <span class="text-muted"> · {{ detail.domain.status || 'unknown' }}</span>
              </p>
              <p v-if="detail.domain.expires_at" class="text-xs text-muted mt-1">
                Expires {{ new Date(detail.domain.expires_at).toLocaleDateString() }}
                <template v-if="detail.domain.days_remaining != null">
                  ({{ detail.domain.days_remaining }} day(s) left)
                </template>
                <template v-if="detail.domain.registrar"> · {{ detail.domain.registrar }}</template>
              </p>
              <p v-else-if="detail.domain.error" class="text-xs text-muted mt-1">
                {{ detail.domain.error }}
              </p>
            </div>
            <span
              class="text-xs font-semibold"
              :class="detail.domain.days_remaining != null && detail.domain.days_remaining <= 30 ? 'text-warn' : 'text-up'"
            >
              {{ detail.domain.days_remaining != null ? detail.domain.days_remaining + 'd' : '—' }}
            </span>
          </div>
        </div>

        <div v-if="detail.monitor.kind === 'keyword'" class="card mt-4 text-sm">
          <p class="text-xs font-semibold text-muted">KEYWORD CHECK</p>
          <p class="mt-1">
            <strong>{{ detail.monitor.config?.keyword }}</strong>
            <span class="text-muted">
              ·
              {{ detail.monitor.config?.match === 'not_contains' ? 'must not appear' : 'must appear' }}
              <template v-if="detail.monitor.config?.case_sensitive"> (case sensitive)</template>
            </span>
          </p>
        </div>

        <div v-if="detail.crawl" class="card mt-4">
          <div class="flex justify-between items-center flex-wrap gap-2">
            <div>
              <p class="text-xs font-semibold text-muted">BROKEN LINKS</p>
              <p v-if="detail.crawl.run" class="text-xs text-muted mt-1">
                Last crawl {{ timeAgo(detail.crawl.run.started_at) }} ·
                {{ detail.crawl.run.pages_crawled }} page(s) ·
                {{ detail.crawl.run.links_checked }} link(s) checked
                <template v-if="detail.crawl.run.error"> · {{ detail.crawl.run.error }}</template>
              </p>
              <p v-else class="text-xs text-muted mt-1">
                No crawl yet — run one now or wait for the daily schedule.
              </p>
            </div>
            <button class="btn btn-ghost btn-sm" :disabled="busy" @click="crawlNow">
              {{ busy ? 'Crawling…' : 'Run crawl now' }}
            </button>
          </div>
          <p class="text-sm mt-3">
            <strong>{{ detail.crawl.broken_links.length }}</strong>
            <span class="text-muted">open broken link(s)</span>
          </p>
          <div v-if="detail.crawl.broken_links.length" class="mt-2 overflow-x-auto">
            <table class="text-xs w-full crawl-table">
              <thead class="text-muted">
                <tr>
                  <th class="text-left py-1">Target</th>
                  <th class="text-left py-1">Found on</th>
                  <th class="text-left py-1">Status</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="link in detail.crawl.broken_links" :key="link.id" class="border-t">
                  <td class="py-1 truncate" style="max-width: 280px">{{ link.target_url }}</td>
                  <td class="py-1 truncate text-muted" style="max-width: 220px">{{ link.source_url }}</td>
                  <td class="py-1">{{ link.status_code || link.error }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <p v-if="detail.monitor.kind === 'heartbeat'" class="text-xs text-muted mt-2">
          Heartbeat:
          <strong>{{ detail.monitor.last_ping_at ? 'last ping ' + timeAgo(detail.monitor.last_ping_at) : 'no ping yet' }}</strong>
          · expected every {{ detail.monitor.check_interval_seconds }}s
          (+{{ detail.monitor.heartbeat_grace_seconds }}s grace)
        </p>

        <IncidentTimeline :monitor-id="detail.monitor.id" />
      </div>
    </div>
  </div>
</template>
