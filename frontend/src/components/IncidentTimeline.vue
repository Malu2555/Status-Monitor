<script setup>
// Incident history for one monitor (newest first, "load more" paging).
import { ref, watch } from 'vue'
import * as monitorsApi from '../api/monitors'
import { timeAgo } from '../utils/format'

const props = defineProps({ monitorId: { type: Number, required: true } })

const incidents = ref([])
const loading = ref(false)
const error = ref('')
const hasMore = ref(false)
const pageSize = 10

function duration(incident) {
  const start = new Date(incident.started_at)
  const end = incident.ended_at ? new Date(incident.ended_at) : new Date()
  const minutes = Math.max(1, Math.round((end - start) / 60000))
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h ${minutes % 60}m`
  return `${Math.floor(hours / 24)}d ${hours % 24}h`
}

async function load(reset = false) {
  loading.value = true
  error.value = ''
  try {
    const offset = reset ? 0 : incidents.value.length
    const rows = await monitorsApi.listIncidents(props.monitorId, pageSize, offset)
    incidents.value = reset ? rows : [...incidents.value, ...rows]
    hasMore.value = rows.length === pageSize
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => props.monitorId, () => load(true), { immediate: true })
</script>

<template>
  <div class="mt-4">
    <p class="text-xs font-semibold text-muted mb-2">INCIDENT HISTORY</p>

    <div v-if="error" class="error-box">{{ error }}</div>
    <p v-else-if="!incidents.length && !loading" class="text-sm text-muted">
      No incidents recorded yet.
    </p>

    <ul v-else>
      <li
        v-for="incident in incidents"
        :key="incident.id"
        class="py-2 text-sm"
        style="border-top: 1px solid var(--color-border)"
      >
        <div class="flex justify-between gap-3 flex-wrap">
          <span>
            <span :class="incident.ended_at ? 'text-up' : 'text-down'">
              {{ incident.ended_at ? 'Resolved' : 'Ongoing' }}
            </span>
            · started {{ timeAgo(incident.started_at) }}
          </span>
          <span class="text-xs text-muted">
            {{ duration(incident) }} · {{ incident.checks_down }} failed check(s)
            <template v-if="incident.last_status_code">· HTTP {{ incident.last_status_code }}</template>
          </span>
        </div>
        <details v-if="incident.postmortem" class="mt-1">
          <summary class="text-xs text-muted">Postmortem draft</summary>
          <pre class="text-xs mt-1" style="white-space: pre-wrap">{{ incident.postmortem }}</pre>
        </details>
      </li>
    </ul>

    <button
      v-if="hasMore"
      class="btn btn-ghost btn-sm mt-2"
      :disabled="loading"
      @click="load(false)"
    >
      {{ loading ? 'Loading…' : 'Load more' }}
    </button>
  </div>
</template>
