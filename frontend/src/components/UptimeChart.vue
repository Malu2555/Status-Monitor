<script setup>
// Bar chart of hourly uptime ratio (Chart.js), rebuilt when series change.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chart } from 'chart.js/auto'

const props = defineProps({
  series: { type: Array, default: () => [] },
  height: { type: Number, default: 140 },
})

const canvasRef = ref(null)
let chart = null

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
  chart.data.labels = props.series.map((s) =>
    new Date(s.bucket).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  )
  chart.data.datasets[0].data = props.series.map((s) => Math.round(s.up_ratio * 100))
  chart.data.datasets[0].backgroundColor = props.series.map((s) =>
    s.up_ratio >= 0.9 ? '#16a34a' : s.up_ratio >= 0.5 ? '#d97706' : '#dc2626',
  )
  chart.update()
}

onMounted(render)
watch(() => props.series, render, { deep: true })
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div class="chart" :style="{ height: height + 'px' }">
    <canvas ref="canvasRef"></canvas>
  </div>
</template>
