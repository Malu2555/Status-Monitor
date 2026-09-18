<script setup>
// Colored status pill (Operational / Down / Pending).
import { statusLabel } from '../utils/format'

const props = defineProps({
  status: { type: String, default: 'unknown' },
})

const state = props.status
</script>

<template>
  <span class="badge" :class="`badge-${state}`">
    <span class="status-dot" :class="`dot-${state}`"></span>
    {{ statusLabel(state) }}
  </span>
</template>
