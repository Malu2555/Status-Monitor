<script setup>
// Branded public status page for one customer (/p/:slug).
// Backend: GET /api/public/statuspages/{slug}.
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import * as monitorsApi from '../api/monitors'
import StatusBadge from '../components/StatusBadge.vue'
import { formatMs, formatUptime, timeAgo } from '../utils/format'

const route = useRoute()
const page = ref(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    page.value = await monitorsApi.publicStatusPage(route.params.slug)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="container">
    <div v-if="loading" class="empty-state mt-6">Loading status page…</div>
    <div v-else-if="error" class="error-box mt-6">{{ error }}</div>
    <template v-else-if="page">
      <div class="text-center">
        <h1 class="text-2xl font-bold" :style="{ color: page.theme_color }">{{ page.title }}</h1>
        <p v-if="page.description" class="text-muted mt-2">{{ page.description }}</p>
        <p class="text-xs text-muted mt-1">Live availability · free, no account needed</p>
      </div>

      <div v-if="page.monitors.length === 0" class="empty-state mt-6">
        No services are published on this page yet.
      </div>
      <div v-else class="monitor-grid mt-6">
        <article v-for="m in page.monitors" :key="m.id" class="card">
          <div class="flex justify-between items-start gap-2">
            <div class="flex-1 truncate">
              <h3 class="font-semibold truncate">{{ m.name }}</h3>
              <a :href="m.url" target="_blank" rel="noopener" class="text-xs text-muted truncate">{{ m.url }}</a>
            </div>
            <StatusBadge :status="m.last_status" />
          </div>
          <div class="flex justify-between text-xs text-muted mt-3 flex-wrap gap-2">
            <span>Response <strong>{{ formatMs(m.last_response_ms) }}</strong></span>
            <span>Checked <strong>{{ timeAgo(m.last_checked_at) }}</strong></span>
            <span>Uptime 24h <strong>{{ formatUptime(m.uptime_24h) }}</strong></span>
          </div>
        </article>
      </div>
    </template>
  </div>
</template>