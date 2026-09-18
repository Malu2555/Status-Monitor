<script setup>
// Login form → auth store → dashboard.
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { logger } from '../utils/logger'

const auth = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  busy.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    router.push({ name: 'dashboard' })
  } catch (e) {
    error.value = e.message || 'Login failed.'
    logger.warn('login failed', error.value)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="container">
    <div class="card auth-card p-6">
      <h1 class="text-xl font-bold">Log in</h1>
      <p class="text-sm text-muted mt-1 mb-4">Access your dashboard.</p>
      <div v-if="error" class="error-box mb-4">{{ error }}</div>
      <form @submit.prevent="submit">
        <div class="field">
          <label class="label" for="username">Username</label>
          <input id="username" v-model="username" class="input" required autocomplete="username" />
        </div>
        <div class="field">
          <label class="label" for="password">Password</label>
          <input id="password" v-model="password" type="password" class="input" required autocomplete="current-password" />
        </div>
        <button type="submit" class="btn btn-primary w-full" :disabled="busy">
          {{ busy ? 'Logging in…' : 'Log in' }}
        </button>
      </form>
      <p class="text-sm text-muted mt-4 text-center">
        No account? <router-link :to="{ name: 'register' }">Create one — free</router-link>
      </p>
    </div>
  </div>
</template>
