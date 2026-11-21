<script setup>
// Plan maintenance windows so scheduled downtime does not page anyone.
import { onMounted, reactive, ref } from 'vue'
import * as maintenanceApi from '../api/maintenance'
import * as monitorsApi from '../api/monitors'
import { logger } from '../utils/logger'

const monitors = ref([])
const windows = ref([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busy = ref('')
const selected = ref('')

const form = reactive({ starts_at: '', ends_at: '', note: '' })

function toIso(localValue) {
  return localValue ? new Date(localValue).toISOString() : ''
}

async function loadMonitors() {
  monitors.value = await monitorsApi.listMonitors()
  if (!selected.value && monitors.value.length) selected.value = monitors.value[0].id
}

async function loadWindows() {
  if (!selected.value) {
    windows.value = []
    return
  }
  loading.value = true
  try {
    windows.value = await maintenanceApi.listWindows(selected.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function create() {
  error.value = ''
  notice.value = ''
  busy.value = 'create'
  try {
    await maintenanceApi.createWindow(selected.value, {
      starts_at: toIso(form.starts_at),
      ends_at: toIso(form.ends_at),
      note: form.note,
    })
    form.starts_at = ''
    form.ends_at = ''
    form.note = ''
    notice.value = 'Maintenance window scheduled — alerts are suppressed while it runs.'
    await loadWindows()
    logger.info('maintenance window created')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function remove(window) {
  if (!window.confirm('Cancel this maintenance window?')) return
  try {
    await maintenanceApi.deleteWindow(selected.value, window.id)
    await loadWindows()
  } catch (e) {
    error.value = e.message
  }
}

function formatRange(window) {
  const start = new Date(window.starts_at).toLocaleString()
  const end = new Date(window.ends_at).toLocaleString()
  return `${start} → ${end}`
}

onMounted(async () => {
  try {
    await loadMonitors()
    await loadWindows()
  } catch (e) {
    error.value = e.message
    loading.value = false
  }
})
</script>

<template>
  <div class="container">
    <h1 class="text-2xl font-bold">Maintenance windows</h1>
    <p class="text-sm text-muted mt-1">
      While a window is active, failed checks do not open incidents or send
      alerts. The monitor itself keeps checking.
    </p>

    <div v-if="error" class="error-box mt-4">{{ error }}</div>
    <div v-if="notice" class="card bg-primary-soft mt-4 text-sm">{{ notice }}</div>

    <div class="card mt-6 p-6">
      <div class="field">
        <label class="label" for="mw-monitor">Monitor</label>
        <select
          id="mw-monitor"
          v-model="selected"
          class="input"
          @change="loadWindows"
        >
          <option v-for="m in monitors" :key="m.id" :value="m.id">{{ m.name }}</option>
        </select>
      </div>
      <p v-if="!monitors.length" class="text-sm text-muted">
        Add a monitor first — windows are scoped to one monitor.
      </p>

      <form v-if="monitors.length" class="mt-2" @submit.prevent="create">
        <div class="md-flex gap-4">
          <div class="field flex-1">
            <label class="label" for="mw-start">Starts</label>
            <input id="mw-start" v-model="form.starts_at" type="datetime-local" class="input" required />
          </div>
          <div class="field flex-1">
            <label class="label" for="mw-end">Ends</label>
            <input id="mw-end" v-model="form.ends_at" type="datetime-local" class="input" required />
          </div>
        </div>
        <div class="field">
          <label class="label" for="mw-note">Note (optional)</label>
          <input id="mw-note" v-model="form.note" class="input" maxlength="200" placeholder="Database migration" />
        </div>
        <button class="btn btn-primary" type="submit" :disabled="busy === 'create'">
          {{ busy === 'create' ? 'Scheduling…' : 'Schedule window' }}
        </button>
      </form>
    </div>

    <div class="mt-6">
      <h2 class="text-lg font-semibold mb-2">Scheduled windows</h2>
      <div v-if="loading" class="empty-state">Loading…</div>
      <div v-else-if="!windows.length" class="empty-state">No windows scheduled.</div>
      <ul v-else>
        <li v-for="window in windows" :key="window.id" class="card mb-3 p-4">
          <div class="flex justify-between items-center gap-3 flex-wrap">
            <div>
              <p class="text-sm font-semibold">{{ formatRange(window) }}</p>
              <p class="text-xs text-muted">{{ window.note || 'no note' }}</p>
            </div>
            <button class="btn btn-ghost btn-sm" @click="remove(window)">Cancel</button>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
