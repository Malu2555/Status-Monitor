<script setup>
// Plan usage bar + Polar checkout (upgrade) and portal (manage) buttons.
import { computed, ref, watch } from 'vue'
import * as billingApi from '../api/billing'

const props = defineProps({
  summary: { type: Object, required: true },
})

const busy = ref('')

const usagePercent = computed(() => {
  const { monitors_used = 0, monitors_limit = 1 } = props.summary
  return Math.min(100, Math.round((monitors_used / monitors_limit) * 100))
})

watch(
  () => props.summary,
  () => {},
)

async function upgrade(plan) {
  busy.value = plan
  try {
    const { url } = await billingApi.checkout(plan)
    window.location.href = url
  } catch (error) {
    window.alert(error.message)
    busy.value = ''
  }
}

async function manage() {
  busy.value = 'portal'
  try {
    const { url } = await billingApi.portal()
    window.location.href = url
  } catch (error) {
    window.alert(error.message)
    busy.value = ''
  }
}
</script>

<template>
  <div class="card bg-primary-soft">
    <div class="flex justify-between items-center flex-wrap gap-3">
      <div>
        <p class="text-xs font-semibold text-primary">{{ summary.plan_label || summary.label }} plan</p>
        <p class="text-sm text-muted mt-1">
          {{ summary.monitors_used }} of {{ summary.monitors_limit }} monitors in use
        </p>
        <div class="uptime-bar mt-2" style="width: 260px; max-width: 100%">
          <span :style="{ width: usagePercent + '%' }"></span>
        </div>
      </div>
      <div class="flex gap-2 flex-wrap">
        <button v-if="summary.plan !== 'pro' && summary.plan !== 'business'" class="btn btn-primary btn-sm" :disabled="busy === 'pro'" @click="upgrade('pro')">
          {{ busy === 'pro' ? 'Redirecting…' : 'Upgrade to Pro — $9/mo' }}
        </button>
        <button v-if="summary.plan !== 'pro' && summary.plan !== 'business'" class="btn btn-ghost btn-sm" :disabled="busy === 'business'" @click="upgrade('business')">
          Business — $29/mo
        </button>
        <button v-if="summary.plan !== 'free'" class="btn btn-ghost btn-sm" :disabled="busy === 'portal'" @click="manage">
          Manage subscription
        </button>
      </div>
    </div>
  </div>
</template>
