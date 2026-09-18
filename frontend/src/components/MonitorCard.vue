<script setup>
// One monitor: name/url, status, latency; click selects, actions edit/delete.
import { formatMs, formatUptime, timeAgo } from '../utils/format'
import StatusBadge from './StatusBadge.vue'

defineProps({
  monitor: { type: Object, required: true },
  showActions: { type: Boolean, default: false },
})

defineEmits(['edit', 'delete', 'select'])
</script>

<template>
  <article class="card clickable" @click="$emit('select')">
    <div class="flex justify-between items-start gap-2">
      <div class="flex-1 truncate">
        <h3 class="text-base font-semibold truncate">{{ monitor.name }}</h3>
        <a class="text-xs text-muted truncate" :href="monitor.url" target="_blank" rel="noopener" @click.stop>{{ monitor.url }}</a>
      </div>
      <StatusBadge :status="monitor.last_status" />
    </div>
    <div class="flex justify-between text-xs text-muted mt-3 flex-wrap gap-2">
      <span>Response <strong class="text-text">{{ formatMs(monitor.last_response_ms) }}</strong></span>
      <span>Checked <strong>{{ timeAgo(monitor.last_checked_at) }}</strong></span>
      <span>Uptime 24h <strong>{{ formatUptime(monitor.uptime_24h) }}</strong></span>
    </div>
    <div v-if="showActions" class="flex justify-end gap-2 mt-3">
      <button class="btn btn-ghost btn-sm" @click.stop="$emit('edit', monitor)">Edit</button>
      <button class="btn btn-danger btn-sm" @click.stop="$emit('delete', monitor)">Delete</button>
    </div>
  </article>
</template>
