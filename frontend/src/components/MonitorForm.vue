<script setup>
// Create/edit monitor form; emits save with the payload or cancel.
// HTTP monitors probe a URL; heartbeat monitors wait for inbound pings.
import { computed, reactive, watch } from 'vue'

const emit = defineEmits(['save', 'cancel'])
const props = defineProps({
  monitor: { type: Object, default: null },
  initialUrl: { type: String, default: '' },
  busy: { type: Boolean, default: false },
})

const INTERVALS = [
  { value: 60, label: 'Every minute' },
  { value: 300, label: 'Every 5 minutes' },
  { value: 900, label: 'Every 15 minutes' },
  { value: 1800, label: 'Every 30 minutes' },
  { value: 3600, label: 'Every hour' },
]

const SLOW_INTERVALS = [
  { value: 3600, label: 'Every hour' },
  { value: 86400, label: 'Daily' },
  { value: 604800, label: 'Weekly' },
]

const GRACES = [
  { value: 60, label: '1 minute' },
  { value: 300, label: '5 minutes' },
  { value: 900, label: '15 minutes' },
  { value: 1800, label: '30 minutes' },
  { value: 3600, label: '1 hour' },
]

const SLOW_KINDS = ['domain', 'broken_links']

function hostnameFromUrl(value) {
  try {
    return new URL(value).hostname.replace(/^www\./, '')
  } catch {
    return value
  }
}

const form = reactive({
  name: '',
  url: '',
  is_public: true,
  check_interval_seconds: 300,
  kind: 'http',
  heartbeat_grace_seconds: 300,
  keyword: '',
  keyword_match: 'contains',
  case_sensitive: false,
  domain: '',
  max_pages: 25,
  max_depth: 2,
  check_images: true,
})

const isHeartbeat = computed(() => form.kind === 'heartbeat')
const isKeyword = computed(() => form.kind === 'keyword')
const isDomain = computed(() => form.kind === 'domain')
const isBrokenLinks = computed(() => form.kind === 'broken_links')
const intervals = computed(() => (SLOW_KINDS.includes(form.kind) ? SLOW_INTERVALS : INTERVALS))
const intervalLabel = computed(() =>
  isDomain.value ? 'Check frequency' : isBrokenLinks.value ? 'Crawl frequency' : isHeartbeat.value ? 'Expected ping interval' : 'Check interval',
)
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
      form.keyword = monitor.config?.keyword || ''
      form.keyword_match = monitor.config?.match || 'contains'
      form.case_sensitive = Boolean(monitor.config?.case_sensitive)
      form.domain = monitor.config?.domain || monitor.url.replace(/^https?:\/\//, '').split('/')[0]
      form.max_pages = monitor.config?.max_pages || 25
      form.max_depth = monitor.config?.max_depth || 2
      form.check_images = monitor.config?.check_images ?? true
    } else {
      form.name = ''
      form.url = ''
      form.is_public = true
      form.check_interval_seconds = 300
      form.kind = 'http'
      form.heartbeat_grace_seconds = 300
      form.keyword = ''
      form.keyword_match = 'contains'
      form.case_sensitive = false
      form.domain = ''
      form.max_pages = 25
      form.max_depth = 2
      form.check_images = true
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

watch(
  () => props.initialUrl,
  (url) => {
    if (url && !props.monitor) {
      form.url = url
      if (!form.name) form.name = hostnameFromUrl(url)
    }
  },
  { immediate: true },
)

watch(
  () => form.kind,
  (kind) => {
    if (SLOW_KINDS.includes(kind) && form.check_interval_seconds < 3600) {
      form.check_interval_seconds = 86400
    } else if (!SLOW_KINDS.includes(kind) && form.check_interval_seconds > 3600) {
      form.check_interval_seconds = 300
    }
  },
)

function submit() {
  const payload = {
    name: form.name,
    is_public: form.is_public,
    check_interval_seconds: form.check_interval_seconds,
  }
  if (!props.monitor) payload.kind = form.kind

  if (isHeartbeat.value) {
    payload.heartbeat_grace_seconds = form.heartbeat_grace_seconds
  } else if (isDomain.value) {
    const domain = form.domain.trim()
    payload.url = domain
    payload.config = { domain }
  } else {
    payload.url = form.url
    if (isKeyword.value) {
      payload.config = {
        keyword: form.keyword,
        match: form.keyword_match,
        case_sensitive: form.case_sensitive,
      }
    } else if (isBrokenLinks.value) {
      payload.config = {
        max_pages: Number(form.max_pages),
        max_depth: Number(form.max_depth),
        check_images: form.check_images,
      }
    }
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
        <option value="keyword">Keyword / content</option>
        <option value="domain">Domain expiry</option>
        <option value="broken_links">Broken links</option>
        <option value="heartbeat">Heartbeat (cron job)</option>
      </select>
    </div>

    <div v-if="!isHeartbeat && !isDomain" class="field">
      <label class="label" for="m-url">URL</label>
      <input id="m-url" v-model="form.url" class="input" type="url" required placeholder="https://example.com" />
      <p class="text-xs text-muted mt-1">
        {{ isBrokenLinks ? 'The crawl starts here and follows same-site links.' : 'http(s) only — private / localhost addresses are rejected for security.' }}
      </p>
    </div>
    <div v-else-if="isDomain" class="field">
      <label class="label" for="m-domain">Domain name</label>
      <input id="m-domain" v-model="form.domain" class="input" required maxlength="253" placeholder="example.com" />
      <p class="text-xs text-muted mt-1">We read the registration expiry from RDAP and alert before it lapses.</p>
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

    <div v-if="isKeyword" class="field">
      <label class="label" for="m-keyword">Text to find</label>
      <input id="m-keyword" v-model="form.keyword" class="input" required maxlength="500" placeholder="Add to cart" />
      <div class="md-flex gap-6 mt-2">
        <div class="field flex-1">
          <label class="label" for="m-keyword-match">Condition</label>
          <select id="m-keyword-match" v-model="form.keyword_match" class="select">
            <option value="contains">Page must contain this text</option>
            <option value="not_contains">Page must not contain this text</option>
          </select>
        </div>
        <div class="field flex items-center gap-2 mt-6">
          <input id="m-case" v-model="form.case_sensitive" type="checkbox" class="checkbox" />
          <label for="m-case" class="text-sm">Case sensitive</label>
        </div>
      </div>
      <p class="text-xs text-muted mt-1">Only server-rendered HTML is inspected (no JavaScript execution).</p>
    </div>

    <div v-if="isBrokenLinks" class="field">
      <div class="md-flex gap-6">
        <div class="field flex-1">
          <label class="label" for="m-pages">Max pages</label>
          <input id="m-pages" v-model.number="form.max_pages" class="input" type="number" min="1" max="100" />
        </div>
        <div class="field flex-1">
          <label class="label" for="m-depth">Max depth</label>
          <input id="m-depth" v-model.number="form.max_depth" class="input" type="number" min="1" max="3" />
        </div>
      </div>
      <label class="flex items-center gap-2 text-sm mt-2">
        <input v-model="form.check_images" type="checkbox" class="checkbox" />
        Also check images
      </label>
      <p class="text-xs text-muted mt-1">Same-site links only, robots.txt respected. JS-rendered content isn't crawled.</p>
    </div>

    <div class="md-flex gap-6">
      <div class="field flex-1">
        <label class="label" for="m-interval">{{ intervalLabel }}</label>
        <select id="m-interval" v-model="form.check_interval_seconds" class="select">
          <option v-for="opt in intervals" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
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
    <div class="flex justify-end gap-2 mt-4 form-actions">
      <button type="button" class="btn btn-ghost" @click="$emit('cancel')">Cancel</button>
      <button type="submit" class="btn btn-primary" :disabled="busy">
        {{ busy ? 'Saving…' : monitor ? 'Save changes' : 'Add monitor' }}
      </button>
    </div>
  </form>
</template>
