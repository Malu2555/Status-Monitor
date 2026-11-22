<script setup>
// Renders one legal document (terms | privacy) served by /api/policies/<slug>.
// The markdown subset supported here: "# ", "## ", "- " bullets and **bold**.
import { computed, onMounted, ref } from 'vue'
import * as policiesApi from '../api/policies'
import { logger } from '../utils/logger'

const props = defineProps({
  slug: { type: String, required: true },
})

const policy = ref(null)
const loading = ref(true)
const error = ref('')

const stripBold = (text) => text.replace(/\*\*/g, '')

// Turn the stored markdown into flat blocks the template can render without v-html.
const blocks = computed(() => {
  const out = []
  let bullets = null
  let lastWasBullet = false
  for (const raw of String(policy.value?.body_md || '').split('\n')) {
    const line = raw.trim()
    if (!line) {
      bullets = null
      lastWasBullet = false
      continue
    }
    if (line.startsWith('## ')) {
      bullets = null
      lastWasBullet = false
      out.push({ type: 'h2', text: stripBold(line.slice(3)) })
      continue
    }
    if (line.startsWith('# ')) {
      bullets = null
      lastWasBullet = false
      out.push({ type: 'h1', text: stripBold(line.slice(2)) })
      continue
    }
    if (line.startsWith('- ')) {
      if (!bullets) {
        bullets = { type: 'ul', items: [] }
        out.push(bullets)
      }
      bullets.items.push(stripBold(line.slice(2)))
      lastWasBullet = true
      continue
    }
    // Indented continuation of the previous bullet.
    if (lastWasBullet && bullets && raw.startsWith(' ')) {
      const last = bullets.items.length - 1
      bullets.items[last] = `${bullets.items[last]} ${stripBold(line)}`
      continue
    }
    bullets = null
    lastWasBullet = false
    out.push({ type: 'p', text: stripBold(line) })
  }
  return out
})

const effective = computed(() =>
  policy.value?.effective_at ? new Date(policy.value.effective_at).toLocaleDateString() : '',
)

onMounted(async () => {
  try {
    policy.value = await policiesApi.getPolicy(props.slug)
  } catch (e) {
    error.value = e.message || 'Could not load this document.'
    logger.warn('policy load failed', props.slug, e.message)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="container">
    <p class="text-sm text-muted">
      <router-link :to="{ name: 'home' }">← Back to home</router-link>
    </p>

    <div v-if="loading" class="empty-state mt-6">Loading…</div>
    <div v-else-if="error" class="error-box mt-6">{{ error }}</div>

    <article v-else class="card p-6 mt-4">
      <p v-if="policy" class="text-xs text-muted">
        Version {{ policy.version }}<template v-if="effective"> · effective {{ effective }}</template>
      </p>
      <template v-for="(block, index) in blocks" :key="index">
        <h1 v-if="block.type === 'h1'" class="text-2xl font-bold mt-2">{{ block.text }}</h1>
        <h2 v-else-if="block.type === 'h2'" class="text-lg font-semibold mt-4">{{ block.text }}</h2>
        <ul v-else-if="block.type === 'ul'" class="mt-2">
          <li v-for="(item, i) in block.items" :key="i" class="text-sm mt-1 ml-4">• {{ item }}</li>
        </ul>
        <p v-else class="text-sm mt-2">{{ block.text }}</p>
      </template>
    </article>
  </div>
</template>
