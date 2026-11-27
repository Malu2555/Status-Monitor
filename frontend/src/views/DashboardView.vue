<script setup>
// Private dashboard: monitor CRUD + uptime chart + plan usage/billing.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as monitorsApi from '../api/monitors'
import MonitorForm from '../components/MonitorForm.vue'
import MonitorRow from '../components/MonitorRow.vue'
import UpgradeCard from '../components/UpgradeCard.vue'
import { useAuthStore } from '../stores/auth'
import { logger } from '../utils/logger'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const monitors = ref([])
const loading = ref(true)
const error = ref('')
const showForm = ref(false)
const editing = ref(null)
const busy = ref(false)
const createdHeartbeat = ref(null)
const prefillUrl = ref(typeof route.query.url === 'string' ? route.query.url : '')
const prefillConsumed = ref(false)

const search = ref('')
const tab = ref('all')
const issueCount = computed(() => monitors.value.filter((m) => m.last_status === 'down').length)
const visibleMonitors = computed(() => {
  const query = search.value.trim().toLowerCase()
  return monitors.value
    .filter((m) => (tab.value === 'issues' ? m.last_status === 'down' : true))
    .filter(
      (m) =>
        !query ||
        m.name.toLowerCase().includes(query) ||
        (m.url || '').toLowerCase().includes(query),
    )
})

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
    await load()
  } catch (e) {
    error.value = e.message
  }
}

function goToMonitor(monitor) {
  router.push({ name: 'monitor', params: { id: monitor.id } })
}

onMounted(load)
</script>

<template>
  <div class="container">
    <div class="flex justify-between items-end flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold">Monitors</h1>
        <p class="text-sm text-muted mt-1">
          Welcome back, {{ auth.user?.username }} — keep an eye on the sites you care about.
        </p>
      </div>
    </div>

    <UpgradeCard v-if="auth.user" :summary="auth.user" class="mt-4" />

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

    <div v-if="error" class="error-box mt-4">{{ error }}</div>

    <div class="monitors-toolbar">
      <input
        v-model="search"
        class="input monitors-search"
        type="search"
        placeholder="Filter monitors…"
        aria-label="Filter monitors"
      />
      <div class="monitors-tabs" role="tablist">
        <button
          type="button"
          class="monitors-tab"
          :class="{ 'is-active': tab === 'all' }"
          role="tab"
          :aria-selected="tab === 'all'"
          @click="tab = 'all'"
        >
          All <span class="count">{{ monitors.length }}</span>
        </button>
        <button
          type="button"
          class="monitors-tab"
          :class="{ 'is-active': tab === 'issues' }"
          role="tab"
          :aria-selected="tab === 'issues'"
          @click="tab = 'issues'"
        >
          Issues <span class="count">{{ issueCount }}</span>
        </button>
      </div>
      <span class="spacer"></span>
      <button
        class="btn btn-primary"
        :disabled="monitors.length >= (auth.user?.monitors_limit ?? 1)"
        @click="openCreate"
      >
        + Add monitor
      </button>
    </div>

    <MonitorForm
      v-if="showForm"
      class="mt-4"
      :monitor="editing"
      :initial-url="editing ? '' : prefillUrl"
      @save="handleSave"
      @cancel="showForm = false"
      :busy="busy"
    />

    <div v-if="loading" class="empty-state mt-6">Loading your monitors…</div>

    <div v-else-if="visibleMonitors.length === 0 && !showForm" class="empty-state mt-6">
      <p class="font-medium">
        {{ monitors.length === 0 ? 'You have no monitors yet' : 'No monitors match this filter' }}
      </p>
      <p class="text-sm mt-1">
        {{
          monitors.length === 0
            ? 'Add your first website to start tracking its uptime.'
            : 'Try a different search or switch to the All tab.'
        }}
      </p>
      <button v-if="monitors.length === 0" class="btn btn-primary mt-4" @click="openCreate">
        + Add your first monitor
      </button>
    </div>

    <div v-else class="monitors-list">
      <div class="monitors-head-row">
        <span>Monitor</span>
        <span>Response</span>
        <span>Status</span>
        <span>Last checked</span>
        <span class="sr-only">Actions</span>
      </div>
      <MonitorRow
        v-for="m in visibleMonitors"
        :key="m.id"
        :monitor="m"
        @select="goToMonitor(m)"
        @edit="openEdit"
        @delete="handleDelete"
      />
    </div>

    <!-- Monitor detail now lives on its own page (/monitors/:id). -->
  </div>
</template>
