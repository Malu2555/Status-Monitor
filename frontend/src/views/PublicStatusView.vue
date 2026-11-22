<script setup>
// Public page: free status feed for everyone, auto-refreshes every 60s.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as monitorsApi from '../api/monitors'
import AppIcon from '../components/AppIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { formatMs, kindLabel, timeAgo } from '../utils/format'
import { logger } from '../utils/logger'

const monitors = ref([])
const loading = ref(true)
const error = ref('')
const lastUpdated = ref(null)
const hasDown = computed(() => monitors.value.some((monitor) => monitor.last_status === 'down'))
const allUp = computed(
  () => monitors.value.length > 0 && monitors.value.every((monitor) => monitor.last_status === 'up'),
)
let timer = null

async function load() {
  try {
    monitors.value = await monitorsApi.publicMonitors()
    lastUpdated.value = new Date()
    error.value = ''
  } catch (e) {
    error.value = e.message
    logger.error('public feed load failed', e.message)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 60000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="container">
    <div class="text-center">
      <h1 class="text-3xl font-extrabold tracking-tight">System Status</h1>
      <p class="text-muted mt-2">Live availability for every monitored site — free, no account needed.</p>
      <p v-if="lastUpdated" class="text-xs text-muted mt-1">
        Last refreshed {{ timeAgo(lastUpdated.toISOString()) }} · auto-updates every 60s
      </p>
    </div>

    <div
      v-if="monitors.length"
      class="status-summary"
      :class="hasDown ? 'is-warn' : 'is-up'"
    >
      <span class="status-summary-icon">
        <AppIcon :name="hasDown ? 'bell' : allUp ? 'check-circle' : 'refresh'" :size="20" />
      </span>
      <span>
        {{
          hasDown
            ? 'Some systems are reporting issues'
            : allUp
              ? 'All monitored systems operational'
              : 'Awaiting the first completed checks'
        }}
      </span>
      <span class="status-summary-meta">{{ monitors.length }} service(s)</span>
    </div>

    <div v-if="error" class="error-box mt-6">{{ error }}</div>

    <div v-if="loading" class="empty-state mt-6">Loading status…</div>

    <div v-else-if="monitors.length === 0" class="empty-state mt-6">
      <p class="font-medium">No monitored sites yet</p>
      <p class="text-sm mt-1">Add your own site for free and it will appear here.</p>
    </div>

    <div v-else class="monitor-grid mt-6">
      <article v-for="m in monitors" :key="m.id" class="card">
        <div class="flex justify-between items-start gap-2">
          <div class="flex-1 truncate">
            <h3 class="font-semibold truncate">{{ m.name }}</h3>
            <p class="text-xs text-muted">{{ kindLabel(m.kind) }}</p>
            <a :href="m.url" target="_blank" rel="noopener" class="text-xs text-muted truncate monitor-url">{{ m.url }}</a>
          </div>
          <StatusBadge :status="m.last_status" />
        </div>
        <div class="flex justify-between text-xs text-muted mt-3 flex-wrap gap-2">
          <span v-if="['http', 'keyword'].includes(m.kind)">
            Response <strong>{{ formatMs(m.last_response_ms) }}</strong>
          </span>
          <span>Checked <strong>{{ timeAgo(m.last_checked_at) }}</strong></span>
          <span>Uptime 24h <strong>{{ m.uptime_24h != null ? m.uptime_24h + '%' : '—' }}</strong></span>
        </div>
      </article>
    </div>

    <div class="text-center mt-8">
      <router-link :to="{ name: 'register' }" class="btn btn-primary btn-lg">Monitor your own site — free</router-link>
    </div>
  </div>
</template>
