<script setup>
// One monitor: name/url, status, latency; click selects, actions edit/delete.
import { computed } from 'vue'
import { formatMs, formatUptime, kindLabel, timeAgo } from '../utils/format'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({
  monitor: { type: Object, required: true },
  showActions: { type: Boolean, default: false },
})

defineEmits(['edit', 'delete', 'select'])

const isHttp = computed(() => ['http', 'keyword'].includes(props.monitor.kind))
const isHeartbeat = computed(() => props.monitor.kind === 'heartbeat')
</script>

<template>
  <article class="card clickable" @click="$emit('select')">
    <div class="flex justify-between items-start gap-2">
      <div class="flex-1 truncate">
        <h3 class="text-base font-semibold truncate">
          {{ monitor.name }}
          <span class="text-xs font-normal text-muted">· {{ kindLabel(monitor.kind) }}</span>
        </h3>
        <a class="text-xs text-muted truncate monitor-url" :href="monitor.url" target="_blank" rel="noopener" @click.stop>{{ monitor.url }}</a>
      </div>
      <StatusBadge :status="monitor.last_status" />
    </div>
    <div class="flex justify-between text-xs text-muted mt-3 flex-wrap gap-2">
      <span v-if="isHttp">Response <strong class="text-text">{{ formatMs(monitor.last_response_ms) }}</strong></span>
      <span v-else-if="isHeartbeat">
        Last ping <strong class="text-text">{{ timeAgo(monitor.last_ping_at) }}</strong>
      </span>
      <span v-else>{{ kindLabel(monitor.kind) }} <strong class="text-text">tracked</strong></span>
      <span>Checked <strong>{{ timeAgo(monitor.last_checked_at) }}</strong></span>
      <span>Uptime 24h <strong>{{ formatUptime(monitor.uptime_24h) }}</strong></span>
    </div>
    <div v-if="showActions" class="flex justify-end gap-2 mt-3">
      <button class="btn btn-ghost btn-sm" @click.stop="$emit('edit', monitor)">Edit</button>
      <button class="btn btn-danger btn-sm" @click.stop="$emit('delete', monitor)">Delete</button>
    </div>
  </article>
</template>
