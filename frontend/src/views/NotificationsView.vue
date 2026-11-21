<script setup>
// Manage alert channels (email / webhook / Slack / Discord / Telegram).
import { computed, onMounted, reactive, ref } from 'vue'
import * as monitorsApi from '../api/monitors'
import * as notificationsApi from '../api/notifications'
import { logger } from '../utils/logger'

const channels = ref([])
const monitors = ref([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busy = ref('')

const form = reactive({ monitor_id: '', kind: 'email', address: '' })

const kinds = [
  { value: 'email', label: 'Email' },
  { value: 'slack', label: 'Slack incoming webhook' },
  { value: 'discord', label: 'Discord webhook' },
  { value: 'telegram', label: 'Telegram (bot_token|chat_id)' },
  { value: 'webhook', label: 'Generic webhook (JSON POST)' },
]

const hints = {
  email: 'ops@example.com',
  slack: 'https://hooks.slack.com/services/T000/B000/XXXX',
  discord: 'https://discord.com/api/webhooks/1234/abcd',
  telegram: '123456789:AAE...|987654321',
  webhook: 'https://example.com/alerts',
}
const hint = computed(() => hints[form.kind] || '')

async function load() {
  loading.value = true
  try {
    const [channelList, monitorList] = await Promise.all([
      notificationsApi.listChannels(),
      monitorsApi.listMonitors(),
    ])
    channels.value = channelList
    monitors.value = monitorList
    if (!form.monitor_id && monitorList.length) form.monitor_id = monitorList[0].id
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function add() {
  error.value = ''
  notice.value = ''
  busy.value = 'add'
  try {
    await notificationsApi.createChannel({
      monitor_id: Number(form.monitor_id),
      kind: form.kind,
      address: form.address,
    })
    form.address = ''
    notice.value = 'Channel added.'
    await load()
    logger.info('notification channel added')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function toggle(channel) {
  error.value = ''
  try {
    await notificationsApi.updateChannel(channel.id, { enabled: !channel.enabled })
    channel.enabled = !channel.enabled
  } catch (e) {
    error.value = e.message
  }
}

async function remove(channel) {
  if (!window.confirm(`Remove the ${channel.kind} channel for ${channel.monitor_name}?`)) return
  try {
    await notificationsApi.deleteChannel(channel.id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function sendTest(channel) {
  error.value = ''
  notice.value = ''
  busy.value = `test-${channel.id}`
  try {
    const result = await notificationsApi.testChannel(channel.id)
    if (result.last_error) {
      error.value = `${result.detail} ${result.last_error}`
    } else {
      notice.value = `${result.detail} (${channel.monitor_name} → ${channel.kind})`
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="container">
    <h1 class="text-2xl font-bold">Notifications</h1>
    <p class="text-sm text-muted mt-1">
      Where we send alerts when a monitor flips DOWN or recovers. You create the
      webhook or bot yourself and paste the address here.
    </p>

    <div v-if="error" class="error-box mt-4">{{ error }}</div>
    <div v-if="notice" class="card bg-primary-soft mt-4 text-sm">{{ notice }}</div>

    <form class="card mt-6 p-6" @submit.prevent="add">
      <h2 class="text-lg font-semibold">Add a channel</h2>
      <div class="md-flex gap-4 mt-3">
        <div class="field flex-1">
          <label class="label" for="ch-monitor">Monitor</label>
          <select id="ch-monitor" v-model="form.monitor_id" class="input" required>
            <option v-for="m in monitors" :key="m.id" :value="m.id">{{ m.name }}</option>
          </select>
        </div>
        <div class="field flex-1">
          <label class="label" for="ch-kind">Type</label>
          <select id="ch-kind" v-model="form.kind" class="input">
            <option v-for="k in kinds" :key="k.value" :value="k.value">{{ k.label }}</option>
          </select>
        </div>
      </div>
      <div class="field">
        <label class="label" for="ch-address">Address</label>
        <input id="ch-address" v-model="form.address" class="input" :placeholder="hint" required />
        <p class="text-xs text-muted mt-1">
          Telegram uses <code>bot_token|chat_id</code>. Everything else takes a URL
          (or an email address for the email type).
        </p>
      </div>
      <p v-if="!monitors.length" class="text-sm text-muted">
        Add a monitor first — channels are scoped to one monitor.
      </p>
      <button class="btn btn-primary" type="submit" :disabled="busy === 'add' || !monitors.length">
        {{ busy === 'add' ? 'Adding…' : 'Add channel' }}
      </button>
    </form>

    <div v-if="loading" class="empty-state mt-6">Loading…</div>
    <div v-else-if="!channels.length" class="empty-state mt-6">
      No channels yet — add one above so you hear about downtime.
    </div>
    <ul v-else class="mt-6">
      <li v-for="channel in channels" :key="channel.id" class="card mb-3 p-4">
        <div class="flex justify-between items-start gap-3 flex-wrap">
          <div class="flex-1">
            <p class="text-sm font-semibold">
              {{ channel.monitor_name }} · {{ channel.kind }}
              <span class="text-xs" :class="channel.enabled ? 'text-up' : 'text-muted'">
                {{ channel.enabled ? 'enabled' : 'paused' }}
              </span>
            </p>
            <p class="text-xs text-muted" style="word-break: break-all">{{ channel.address }}</p>
          </div>
          <div class="flex gap-2 flex-wrap">
            <button
              class="btn btn-ghost btn-sm"
              :disabled="busy === `test-${channel.id}`"
              @click="sendTest(channel)"
            >
              {{ busy === `test-${channel.id}` ? 'Sending…' : 'Test' }}
            </button>
            <button class="btn btn-ghost btn-sm" @click="toggle(channel)">
              {{ channel.enabled ? 'Pause' : 'Resume' }}
            </button>
            <button class="btn btn-danger btn-sm" @click="remove(channel)">Delete</button>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
