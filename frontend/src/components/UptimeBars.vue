<script setup>
// One bar per uptime bucket (green healthy / amber degraded / red down / neutral empty).
defineProps({
  buckets: { type: Array, default: () => [] },
})

function tone(b) {
  if (!b.samples) return 'empty'
  if (b.up_ratio >= 0.9) return 'up'
  if (b.up_ratio >= 0.5) return 'warn'
  return 'down'
}

function tip(b) {
  if (!b.samples) return 'No checks in this interval'
  return `${b.samples} check(s) · ${Math.round(b.up_ratio * 100)}% up`
}
</script>

<template>
  <div class="uptime-bars">
    <span
      v-for="(b, i) in buckets"
      :key="i"
      class="uptime-bars__bar"
      :class="`is-${tone(b)}`"
      :title="tip(b)"
    ></span>
  </div>
</template>
