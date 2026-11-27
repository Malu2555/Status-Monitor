<script setup>
// Latency line chart (Chart.js) for the monitor detail Uptime tab.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chart } from 'chart.js/auto'
import { useTheme } from '../composables/useTheme'

const props = defineProps({
  buckets: { type: Array, default: () => [] },
  height: { type: Number, default: 160 },
})

const { resolved } = useTheme()
const canvasRef = ref(null)
let chart = null

function token(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

function palette() {
  return {
    line: token('--color-primary', '#10b981'),
    fill: token('--color-primary-tint', 'rgba(16, 185, 129, 0.15)'),
    text: token('--color-muted', '#64748b'),
    grid: token('--color-border', '#e2e8f0'),
  }
}

function labels() {
  return props.buckets.map((b) =>
    new Date(b.bucket).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  )
}

function render() {
  if (!canvasRef.value) return
  const colors = palette()
  if (!chart) {
    chart = new Chart(canvasRef.value, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'latency (ms)',
            data: [],
            borderColor: colors.line,
            backgroundColor: colors.fill,
            fill: true,
            tension: 0.35,
            spanGaps: true,
            pointRadius: 0,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { callback: (value) => `${value}ms` } },
          x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
        },
      },
    })
  }
  chart.data.labels = labels()
  chart.data.datasets[0].data = props.buckets.map((b) => b.response_avg_ms)
  chart.data.datasets[0].borderColor = colors.line
  chart.data.datasets[0].backgroundColor = colors.fill
  chart.options.scales.y.ticks.color = colors.text
  chart.options.scales.y.grid.color = colors.grid
  chart.options.scales.x.ticks.color = colors.text
  chart.update()
}

onMounted(render)
watch(() => props.buckets, render, { deep: true })
watch(resolved, render)
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div class="chart" :style="{ height: height + 'px' }">
    <canvas ref="canvasRef"></canvas>
  </div>
</template>
