<script setup>
// One row in the monitors list: status dot + name/url, latency, status, checked.
// Row click selects (opens the inline detail); action buttons emit edit/delete.
import { computed } from 'vue'
import { formatMs, kindLabel, timeAgo } from '../utils/format'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({
  monitor: { type: Object, required: true },
})

defineEmits(['select', 'edit', 'delete'])

const isHttp = computed(() => ['http', 'keyword'].includes(props.monitor.kind))
const isHeartbeat = computed(() => props.monitor.kind === 'heartbeat')
const dotClass = computed(() => `dot-${props.monitor.last_status || 'unknown'}`)

const responseText = computed(() => {
  if (isHttp.value) return formatMs(props.monitor.last_response_ms)
  if (isHeartbeat.value) return timeAgo(props.monitor.last_ping_at)
  return kindLabel(props.monitor.kind)
})
</script>

<template>
  <div
    class="monitor-row"
    role="button"
    tabindex="0"
    @click="$emit('select', monitor)"
    @keydown.enter="$emit('select', monitor)"
  >
    <div class="monitor-row__main">
      <span class="status-dot" :class="dotClass"></span>
      <div>
        <span class="monitor-row__name">{{ monitor.name }}</span>
        <span class="monitor-row__kind">· {{ kindLabel(monitor.kind) }}</span>
        <a
          v-if="monitor.url"
          class="monitor-row__url truncate"
          :href="monitor.url"
          target="_blank"
          rel="noopener"
          @click.stop
        >
          {{ monitor.url }}
        </a>
      </div>
    </div>
    <div class="monitor-row__perf text-sm text-muted">{{ responseText }}</div>
    <div class="monitor-row__status"><StatusBadge :status="monitor.last_status" /></div>
    <div class="monitor-row__checked text-xs text-muted">{{ timeAgo(monitor.last_checked_at) }}</div>
    <div class="monitor-row__actions">
      <button class="btn btn-ghost btn-sm" @click.stop="$emit('edit', monitor)">Edit</button>
      <button class="btn btn-danger btn-sm" @click.stop="$emit('delete', monitor)">Delete</button>
    </div>
  </div>
</template>
