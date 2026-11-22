<script setup>
// Handles both signup verification and pending email-change links.
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import * as authApi from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { logger } from '../utils/logger'

const route = useRoute()
const auth = useAuthStore()

const state = ref('working') // working | ok | error
const message = ref('Confirming your link…')

onMounted(async () => {
  const token = String(route.query.token || '')
  if (!token) {
    state.value = 'error'
    message.value = 'This link is missing its token.'
    return
  }
  try {
    await authApi.verifyEmail(token)
    state.value = 'ok'
    message.value = 'Email confirmed. You can close this page.'
    if (auth.isAuthenticated && auth.user) {
      // Keep the badge in the header accurate after an email change.
      try {
        auth.user = await authApi.me()
      } catch (e) {
        logger.debug('profile refresh after verification failed', e.message)
      }
    }
  } catch (e) {
    state.value = 'error'
    message.value = e.message || 'This link is invalid or has expired.'
  }
})
</script>

<template>
  <div class="container">
    <div class="card auth-card p-6 text-center">
      <h1 class="text-xl font-bold">Email verification</h1>
      <p v-if="state === 'working'" class="text-sm text-muted mt-3">{{ message }}</p>
      <p v-else-if="state === 'ok'" class="text-sm mt-3">{{ message }}</p>
      <p v-else class="error-box mt-3">{{ message }}</p>

      <div class="mt-4 flex justify-center gap-2">
        <router-link v-if="auth.isAuthenticated" :to="{ name: 'dashboard' }" class="btn btn-primary">
          Go to dashboard
        </router-link>
        <router-link v-else :to="{ name: 'login' }" class="btn btn-primary">Log in</router-link>
        <router-link :to="{ name: 'status' }" class="btn btn-ghost">Live status</router-link>
      </div>
    </div>
  </div>
</template>
