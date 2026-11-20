<script setup>
// Manage branded public status pages (rendered at /p/<slug>).
import { onMounted, reactive, ref } from 'vue'
import * as monitorsApi from '../api/monitors'
import * as statusPagesApi from '../api/statuspages'
import { logger } from '../utils/logger'

const pages = ref([])
const monitors = ref([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busy = ref('')
const showForm = ref(false)
const editingId = ref(null)

const form = reactive({
  slug: '',
  title: '',
  description: '',
  theme_color: '#0f766e',
  is_public: true,
  is_active: true,
  monitor_ids: [],
})

function resetForm() {
  form.slug = ''
  form.title = ''
  form.description = ''
  form.theme_color = '#0f766e'
  form.is_public = true
  form.is_active = true
  form.monitor_ids = []
}

async function load() {
  loading.value = true
  try {
    const [pageList, monitorList] = await Promise.all([
      statusPagesApi.listStatusPages(),
      monitorsApi.listMonitors(),
    ])
    pages.value = pageList
    monitors.value = monitorList
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function syncSlug() {
  if (editingId.value) return
  form.slug = form.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
}

function openCreate() {
  editingId.value = null
  resetForm()
  showForm.value = true
  error.value = ''
  notice.value = ''
}

function openEdit(page) {
  editingId.value = page.id
  form.slug = page.slug
  form.title = page.title
  form.description = page.description
  form.theme_color = page.theme_color
  form.is_public = page.is_public
  form.is_active = page.is_active
  form.monitor_ids = [...page.monitor_ids]
  showForm.value = true
  error.value = ''
  notice.value = ''
}

async function save() {
  error.value = ''
  notice.value = ''
  busy.value = 'save'
  try {
    const payload = { ...form }
    if (editingId.value) await statusPagesApi.updateStatusPage(editingId.value, payload)
    else await statusPagesApi.createStatusPage(payload)
    notice.value = 'Status page saved.'
    showForm.value = false
    editingId.value = null
    await load()
    logger.info('status page saved')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function remove(page) {
  if (!window.confirm(`Delete the status page “${page.title}”?`)) return
  try {
    await statusPagesApi.deleteStatusPage(page.id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
</script>

<template>
  <div class="container">
    <div class="flex justify-between items-center flex-wrap gap-3">
      <div>
        <h1 class="text-2xl font-bold">Status pages</h1>
        <p class="text-sm text-muted mt-1">Branded public pages showing a subset of your monitors.</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">+ New status page</button>
    </div>

    <div v-if="error" class="error-box mt-6">{{ error }}</div>
    <div v-if="notice" class="card bg-primary-soft mt-6 text-sm">{{ notice }}</div>

    <form v-if="showForm" class="panel mt-6" @submit.prevent="save">
      <h2 class="text-lg font-semibold mb-4">{{ editingId ? 'Edit status page' : 'New status page' }}</h2>
      <div class="md-flex gap-6">
        <div class="field flex-1">
          <label class="label" for="sp-title">Title</label>
          <input id="sp-title" v-model="form.title" class="input" required maxlength="120" @input="syncSlug" />
        </div>
        <div class="field flex-1">
          <label class="label" for="sp-slug">Slug</label>
          <input id="sp-slug" v-model="form.slug" class="input" required pattern="[a-z0-9][a-z0-9-]*" maxlength="60" placeholder="acme" />
          <p class="text-xs text-muted mt-1">Public URL: /p/{{ form.slug || 'slug' }}</p>
        </div>
      </div>
      <div class="field">
        <label class="label" for="sp-description">Description</label>
        <input id="sp-description" v-model="form.description" class="input" maxlength="300" />
      </div>
      <div class="md-flex gap-6">
        <div class="field">
          <label class="label" for="sp-color">Theme color</label>
          <input id="sp-color" v-model="form.theme_color" class="input" type="color" />
        </div>
        <div class="field flex items-center gap-2 mt-6">
          <input id="sp-public" v-model="form.is_public" type="checkbox" class="checkbox" />
          <label for="sp-public" class="text-sm">Public</label>
          <input id="sp-active" v-model="form.is_active" type="checkbox" class="checkbox ml-4" />
          <label for="sp-active" class="text-sm">Active</label>
        </div>
      </div>
      <div class="field">
        <label class="label">Monitors on this page</label>
        <p v-if="monitors.length === 0" class="text-sm text-muted">No monitors yet.</p>
        <div v-else class="flex flex-wrap gap-3">
          <label v-for="m in monitors" :key="m.id" class="flex items-center gap-2 text-sm">
            <input v-model="form.monitor_ids" type="checkbox" :value="m.id" class="checkbox" />
            {{ m.name }}
          </label>
        </div>
      </div>
      <div class="flex justify-end gap-2 mt-4">
        <button type="button" class="btn btn-ghost" @click="showForm = false">Cancel</button>
        <button type="submit" class="btn btn-primary" :disabled="busy === 'save'">
          {{ busy === 'save' ? 'Saving…' : 'Save' }}
        </button>
      </div>
    </form>

    <div v-if="loading" class="empty-state mt-6">Loading…</div>
    <div v-else-if="pages.length === 0 && !showForm" class="empty-state mt-6">
      No status pages yet — create one to publish a branded page.
    </div>
    <div v-else class="monitor-grid mt-6">
      <article v-for="p in pages" :key="p.id" class="card">
        <div class="flex justify-between items-start gap-2">
          <div class="flex-1 truncate">
            <h3 class="font-semibold truncate" :style="{ color: p.theme_color }">{{ p.title }}</h3>
            <p class="text-xs text-muted">/p/{{ p.slug }} · {{ p.monitor_ids.length }} monitor(s)</p>
          </div>
          <span class="text-xs" :class="p.is_public && p.is_active ? 'text-up' : 'text-muted'">
            {{ p.is_public && p.is_active ? 'Public' : 'Hidden' }}
          </span>
        </div>
        <div class="flex justify-end gap-2 mt-3 flex-wrap">
          <router-link :to="'/p/' + p.slug" target="_blank" class="btn btn-ghost btn-sm">View</router-link>
          <button class="btn btn-ghost btn-sm" @click="openEdit(p)">Edit</button>
          <button class="btn btn-danger btn-sm" @click="remove(p)">Delete</button>
        </div>
      </article>
    </div>
  </div>
</template>
