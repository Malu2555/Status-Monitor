<script setup>
// Registration form → auth store → dashboard.
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { logger } from '../utils/logger'

const auth = useAuthStore()
const router = useRouter()

const username = ref('')
const email = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  if (password.value !== confirm.value) {
    error.value = 'Passwords do not match.'
    return
  }
  busy.value = true
  try {
    await auth.register({ username: username.value, email: email.value, password: password.value })
    router.push({ name: 'dashboard' })
  } catch (e) {
    error.value = e.message || 'Registration failed.'
    logger.warn('registration failed', error.value)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="container">
    <div class="card auth-card p-6">
      <h1 class="text-xl font-bold">Create your account</h1>
      <p class="text-sm text-muted mt-1 mb-4">Free plan: 1 monitor with 5-minute checks.</p>
      <div v-if="error" class="error-box mb-4">{{ error }}</div>
      <form @submit.prevent="submit">
        <div class="field">
          <label class="label" for="username">Username</label>
          <input id="username" v-model="username" class="input" required minlength="3" maxlength="30" autocomplete="username" />
        </div>
        <div class="field">
          <label class="label" for="email">Email</label>
          <input id="email" v-model="email" type="email" class="input" required autocomplete="email" />
        </div>
        <div class="field">
          <label class="label" for="password">Password</label>
          <input id="password" v-model="password" type="password" class="input" required minlength="8" autocomplete="new-password" />
        </div>
        <div class="field">
          <label class="label" for="confirm">Confirm password</label>
          <input id="confirm" v-model="confirm" type="password" class="input" required minlength="8" autocomplete="new-password" />
        </div>
        <button type="submit" class="btn btn-primary w-full" :disabled="busy">
          {{ busy ? 'Creating account…' : 'Create account' }}
        </button>
      </form>
      <p class="text-sm text-muted mt-4 text-center">
        Already registered? <router-link :to="{ name: 'login' }">Log in</router-link>
      </p>
    </div>
  </div>
</template>
