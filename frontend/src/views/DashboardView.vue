<script setup>
// Private dashboard: monitor CRUD + uptime chart + plan usage/billing.
import { onMounted, ref } from 'vue'
import * as monitorsApi from '../api/monitors'
import MonitorCard from '../components/MonitorCard.vue'
import MonitorForm from '../components/MonitorForm.vue'
import UptimeChart from '../components/UptimeChart.vue'
import UpgradeCard from '../components/UpgradeCard.vue'
import { useAuthStore } from '../stores/auth'
import { formatMs, statusLabel, timeAgo } from '../utils/format'
import { logger } from '../utils/logger'

const auth = useAuthStore()

const monitors = ref([])
const loading = ref(true)
const error = ref('')
const showForm = ref(false)
const editing = ref(null)
const detail = ref(null) // { monitor, stats }
const busy = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    monitors.value = await monitorsApi.listMonitors()
    await auth.refreshBilling()
  } catch (e) {
    error.value = e.message
    logger.error('dashboard load failed', e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
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
    if (editing.value) await monitorsApi.updateMonitor(editing.value.id, payload)
    else await monitorsApi.createMonitor(payload)
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
    detail.value = { monitor, stats: await monitorsApi.monitorStats(monitor.id, 24) }
  } catch (e) {
    error.value = e.message
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

    <div v-if="error" class="error-box mt-6">{{ error }}</div>

    <MonitorForm
      v-if="showForm"
      class="mt-6"
      :monitor="editing"
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
            <h2 class="text-lg font-semibold">{{ detail.monitor.name }}</h2>
            <p class="text-xs text-muted mt-1">
              {{ statusLabel(detail.monitor.last_status) }} · last checked
              {{ timeAgo(detail.monitor.last_checked_at) }} · response
              {{ formatMs(detail.monitor.last_response_ms) }}
            </p>
          </div>
          <span class="text-sm font-semibold text-up">
            {{ detail.stats.uptime_percent != null ? detail.stats.uptime_percent + '% uptime (24h)' : 'no data yet' }}
          </span>
        </div>
        <UptimeChart v-if="detail.stats.series.length" :series="detail.stats.series" :height="160" />
        <p v-else class="text-sm text-muted">No checks recorded yet — they appear after the first scheduled run.</p>
      </div>
    </div>
  </div>
</template>
