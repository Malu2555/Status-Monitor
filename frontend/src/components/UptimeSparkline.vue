<script setup>
// Lightweight inline line chart (no Chart.js) for the uptime detail page.
import { computed } from 'vue'

const props = defineProps({
  values: { type: Array, default: () => [] }, // numbers, or null for gaps
  height: { type: Number, default: 120 },
  color: { type: String, default: 'var(--color-primary)' },
})

const W = 100
const H = 100

const pts = computed(() => {
  const vals = props.values.map((v) => (typeof v === 'number' ? v : null))
  const nums = vals.filter((v) => v != null)
  if (!nums.length) return []
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const span = max - min || 1
  const n = vals.length
  const out = []
  vals.forEach((v, i) => {
    if (v == null) return
    const x = n === 1 ? W : (i / (n - 1)) * W
    const y = H - ((v - min) / span) * (H - 10) - 5
    out.push([x, y])
  })
  return out
})

const line = computed(() =>
  pts.value.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`).join(' '),
)
const area = computed(() => (line.value ? `${line.value} L${W} ${H} L0 ${H} Z` : ''))
</script>

<template>
  <svg
    :viewBox="`0 0 ${W} ${H}`"
    :style="{ height: height + 'px', width: '100%' }"
    preserveAspectRatio="none"
    aria-hidden="true"
  >
    <path v-if="area" :d="area" :fill="color" opacity="0.12" />
    <path
      v-if="line"
      :d="line"
      fill="none"
      :stroke="color"
      stroke-width="2"
      vector-effect="non-scaling-stroke"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>
