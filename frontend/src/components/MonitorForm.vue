<script setup>
// Create/edit monitor form; emits save with the payload or cancel.
import { reactive, watch } from 'vue'

const emit = defineEmits(['save', 'cancel'])
const props = defineProps({
  monitor: { type: Object, default: null },
})

const INTERVALS = [
  { value: 60, label: 'Every minute' },
  { value: 300, label: 'Every 5 minutes' },
  { value: 900, label: 'Every 15 minutes' },
  { value: 1800, label: 'Every 30 minutes' },
  { value: 3600, label: 'Every hour' },
]

const form = reactive({
  name: '',
  url: '',
  is_public: true,
  check_interval_seconds: 300,
})

watch(
  () => props.monitor,
  (monitor) => {
    if (monitor) {
      form.name = monitor.name
      form.url = monitor.url
      form.is_public = monitor.is_public
      form.check_interval_seconds = monitor.check_interval_seconds
    } else {
      form.name = ''
      form.url = ''
      form.is_public = true
      form.check_interval_seconds = 300
    }
  },
  { immediate: true },
)

function submit() {
  emit('save', { ...form })
}
</script>

<template>
  <form class="panel" @submit.prevent="submit">
    <h2 class="text-lg font-semibold mb-4">{{ monitor ? 'Edit monitor' : 'Add a monitor' }}</h2>
    <div class="field">
      <label class="label" for="m-name">Name</label>
      <input id="m-name" v-model="form.name" class="input" required maxlength="100" placeholder="My awesome site" />
    </div>
    <div class="field">
      <label class="label" for="m-url">URL</label>
      <input id="m-url" v-model="form.url" class="input" type="url" required placeholder="https://example.com" />
      <p class="text-xs text-muted mt-1">http(s) only — private / localhost addresses are rejected for security.</p>
    </div>
    <div class="md-flex gap-6">
      <div class="field flex-1">
        <label class="label" for="m-interval">Check interval</label>
        <select id="m-interval" v-model="form.check_interval_seconds" class="select">
          <option v-for="opt in INTERVALS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <div class="field">
        <label class="label">Visibility</label>
        <div class="flex items-center gap-2 mt-1">
          <input id="m-public" v-model="form.is_public" type="checkbox" class="checkbox" />
          <label for="m-public" class="text-sm">Show on the public status page</label>
        </div>
      </div>
    </div>
    <div class="flex justify-end gap-2 mt-4">
      <button type="button" class="btn btn-ghost" @click="$emit('cancel')">Cancel</button>
      <button type="submit" class="btn btn-primary">{{ monitor ? 'Save changes' : 'Add monitor' }}</button>
    </div>
  </form>
</template>
