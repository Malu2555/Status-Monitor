<script setup>
// Create/edit monitor form; emits save with the payload or cancel.
// HTTP monitors probe a URL; heartbeat monitors wait for inbound pings.
import { computed, reactive, watch } from 'vue'

const emit = defineEmits(['save', 'cancel'])
const props = defineProps({
  monitor: { type: Object, default: null },
})

const INTERVALS = [
  { value: 60, label: 'Every minute' },
  { value: 300, label: 'Every 5 minutes' },
  { value: 900, label: 'Every 15 minutes' },
  { value: 1800, label: 'Every 30 minutes' },
  { value: 3600, label: 'Every hour' },
]

const GRACES = [
  { value: 60, label: '1 minute' },
  { value: 300, label: '5 minutes' },
  { value: 900, label: '15 minutes' },
  { value: 1800, label: '30 minutes' },
  { value: 3600, label: '1 hour' },
]

const form = reactive({
  name: '',
  url: '',
  is_public: true,
  check_interval_seconds: 300,
  kind: 'http',
  heartbeat_grace_seconds: 300,
})

const isHeartbeat = computed(() => form.kind === 'heartbeat')
const pingUrl = computed(() => {
  if (!props.monitor?.heartbeat_token) return ''
  return `${window.location.origin}/api/public/heartbeat/${props.monitor.heartbeat_token}`
})

watch(
  () => props.monitor,
  (monitor) => {
    if (monitor) {
      form.name = monitor.name
      form.url = monitor.url
      form.is_public = monitor.is_public
      form.check_interval_seconds = monitor.check_interval_seconds
      form.kind = monitor.kind || 'http'
      form.heartbeat_grace_seconds = monitor.heartbeat_grace_seconds || 300
    } else {
      form.name = ''
      form.url = ''
      form.is_public = true
      form.check_interval_seconds = 300
      form.kind = 'http'
      form.heartbeat_grace_seconds = 300
    }
  },
  { immediate: true },
)

async function copyPing() {
  try {
    await navigator.clipboard.writeText(pingUrl.value)
  } catch {
    /* clipboard unavailable (insecure context) — the input is selectable */
  }
}

function submit() {
  const payload = {
    name: form.name,
    is_public: form.is_public,
    check_interval_seconds: form.check_interval_seconds,
  }
  if (!props.monitor) {
    payload.kind = form.kind
    payload.heartbeat_grace_seconds = form.heartbeat_grace_seconds
    if (form.kind === 'http') payload.url = form.url
  } else if (props.monitor.kind === 'http') {
    payload.url = form.url
  } else {
    payload.heartbeat_grace_seconds = form.heartbeat_grace_seconds
  }
  emit('save', payload)
}
</script>

<template>
  <form class="panel" @submit.prevent="submit">
    <h2 class="text-lg font-semibold mb-4">{{ monitor ? 'Edit monitor' : 'Add a monitor' }}</h2>
    <div class="field">
      <label class="label" for="m-name">Name</label>
      <input id="m-name" v-model="form.name" class="input" required maxlength="100" placeholder="My awesome site" />
    </div>

    <div v-if="!monitor" class="field">
      <label class="label" for="m-kind">Type</label>
      <select id="m-kind" v-model="form.kind" class="select">
        <option value="http">HTTP(s) URL</option>
        <option value="heartbeat">Heartbeat (cron job)</option>
      </select>
    </div>

    <div v-if="!isHeartbeat" class="field">
      <label class="label" for="m-url">URL</label>
      <input id="m-url" v-model="form.url" class="input" type="url" required placeholder="https://example.com" />
      <p class="text-xs text-muted mt-1">http(s) only — private / localhost addresses are rejected for security.</p>
    </div>
    <div v-else class="field">
      <p class="text-xs text-muted">
        We expect an inbound ping from your cron job. If none arrives within the
        interval plus grace period, the monitor goes down.
      </p>
      <div v-if="pingUrl" class="mt-2">
        <label class="label">Ping URL</label>
        <input class="input" :value="pingUrl" readonly />
        <button type="button" class="btn btn-ghost btn-sm mt-2" @click="copyPing">Copy ping URL</button>
      </div>
      <p v-else class="text-xs text-muted mt-2">The ping URL is shown right after you save.</p>
    </div>

    <div class="md-flex gap-6">
      <div class="field flex-1">
        <label class="label" for="m-interval">{{ isHeartbeat ? 'Expected ping interval' : 'Check interval' }}</label>
        <select id="m-interval" v-model="form.check_interval_seconds" class="select">
          <option v-for="opt in INTERVALS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <div v-if="isHeartbeat" class="field flex-1">
        <label class="label" for="m-grace">Grace period</label>
        <select id="m-grace" v-model="form.heartbeat_grace_seconds" class="select">
          <option v-for="opt in GRACES" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <div class="field">
        <label class="label">Visibility</label>
        <div class="flex items-center gap-2 mt-1">
          <input id="m-public" v-model="form.is_public" type="checkbox" class="checkbox" />
          <label for="m-public" class="text-sm">Show on the public status page</label>
        </div>
      </div>
    </div>
    <div class="flex justify-end gap-2 mt-4">
      <button type="button" class="btn btn-ghost" @click="$emit('cancel')">Cancel</button>
      <button type="submit" class="btn btn-primary">{{ monitor ? 'Save changes' : 'Add monitor' }}</button>
    </div>
  </form>
</template>
