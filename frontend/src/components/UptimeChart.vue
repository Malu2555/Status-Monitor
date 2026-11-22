<script setup>
// Bar chart of hourly uptime ratio (Chart.js), rebuilt when series or theme changes.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chart } from 'chart.js/auto'
import { useTheme } from '../composables/useTheme'

const props = defineProps({
  series: { type: Array, default: () => [] },
  height: { type: Number, default: 140 },
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
    up: token('--color-up', '#10b981'),
    warn: token('--color-warn', '#d97706'),
    down: token('--color-down', '#dc2626'),
    text: token('--color-muted', '#64748b'),
    grid: token('--color-border', '#e2e8f0'),
  }
}

function applyTheme() {
  if (!chart) return
  const colors = palette()
  chart.options.scales.y.ticks.color = colors.text
  chart.options.scales.y.grid.color = colors.grid
  chart.options.scales.x.ticks.color = colors.text
  chart.data.datasets[0].backgroundColor = props.series.map((s) =>
    s.up_ratio >= 0.9 ? colors.up : s.up_ratio >= 0.5 ? colors.warn : colors.down,
  )
  chart.update()
}

function render() {
  if (!canvasRef.value) return
  if (!chart) {
    chart = new Chart(canvasRef.value, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [
          {
            label: 'uptime %',
            data: [],
            backgroundColor: [],
            borderRadius: 3,
            maxBarThickness: 22,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, max: 100, ticks: { callback: (v) => `${v}%` } },
          x: { grid: { display: false } },
        },
      },
    })
  }
  const colors = palette()
  chart.data.labels = props.series.map((s) =>
    new Date(s.bucket).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  )
  chart.data.datasets[0].data = props.series.map((s) => Math.round(s.up_ratio * 100))
  chart.data.datasets[0].backgroundColor = props.series.map((s) =>
    s.up_ratio >= 0.9 ? colors.up : s.up_ratio >= 0.5 ? colors.warn : colors.down,
  )
  chart.options.scales.y.ticks.color = colors.text
  chart.options.scales.y.grid.color = colors.grid
  chart.options.scales.x.ticks.color = colors.text
  chart.update()
}

onMounted(render)
watch(() => props.series, render, { deep: true })
watch(resolved, applyTheme)
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div class="chart" :style="{ height: height + 'px' }">
    <canvas ref="canvasRef"></canvas>
  </div>
</template>
