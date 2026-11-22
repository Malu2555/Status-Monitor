<script setup>
// Self-service account management: password, email, sessions, deletion.
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as accountApi from '../api/account'
import { useAuthStore } from '../stores/auth'
import { logger } from '../utils/logger'

const auth = useAuthStore()
const router = useRouter()

const passwordForm = reactive({ current_password: '', new_password: '', confirm: '' })
const emailForm = reactive({ new_email: '', current_password: '' })
const deleteForm = reactive({ current_password: '', confirmText: '' })

const busy = ref('')
const error = ref('')
const notice = ref('')

function reset() {
  error.value = ''
  notice.value = ''
}

async function changePassword() {
  reset()
  if (passwordForm.new_password !== passwordForm.confirm) {
    error.value = 'New passwords do not match.'
    return
  }
  busy.value = 'password'
  try {
    const data = await accountApi.changePassword({
      current_password: passwordForm.current_password,
      new_password: passwordForm.new_password,
    })
    auth.setSession(data)
    passwordForm.current_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm = ''
    notice.value = 'Password changed. Other sessions were signed out.'
    logger.info('password changed')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function changeEmail() {
  reset()
  busy.value = 'email'
  try {
    const data = await accountApi.changeEmail({
      new_email: emailForm.new_email,
      current_password: emailForm.current_password,
    })
    emailForm.current_password = ''
    notice.value = data.detail
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function revokeOthers() {
  reset()
  busy.value = 'sessions'
  try {
    const data = await accountApi.revokeOtherSessions()
    auth.setSession(data)
    notice.value = 'All other sessions were signed out.'
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function deleteAccount() {
  reset()
  if (deleteForm.confirmText !== auth.user?.username) {
    error.value = 'Type your username exactly to confirm.'
    return
  }
  busy.value = 'delete'
  try {
    await accountApi.deleteAccount({ current_password: deleteForm.current_password })
    logger.warn('account deleted')
    auth.clear()
    router.push({ name: 'home' })
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="container">
    <h1 class="text-2xl font-bold">Account settings</h1>
    <p class="text-sm text-muted mt-1">
      Signed in as <strong>{{ auth.user?.username }}</strong> · {{ auth.user?.email }}
    </p>

    <div v-if="error" class="error-box mt-4">{{ error }}</div>
    <div v-if="notice" class="card bg-primary-soft mt-4 text-sm">{{ notice }}</div>

    <div class="card mt-6 p-6">
      <h2 class="text-lg font-semibold">Change password</h2>
      <form class="mt-3" @submit.prevent="changePassword">
        <div class="field">
          <label class="label" for="pw-current">Current password</label>
          <input id="pw-current" v-model="passwordForm.current_password" type="password" class="input" required autocomplete="current-password" />
        </div>
        <div class="field">
          <label class="label" for="pw-new">New password</label>
          <input id="pw-new" v-model="passwordForm.new_password" type="password" class="input" required minlength="8" autocomplete="new-password" />
        </div>
        <div class="field">
          <label class="label" for="pw-confirm">Confirm new password</label>
          <input id="pw-confirm" v-model="passwordForm.confirm" type="password" class="input" required minlength="8" autocomplete="new-password" />
        </div>
        <button class="btn btn-primary" type="submit" :disabled="busy === 'password'">
          {{ busy === 'password' ? 'Saving…' : 'Update password' }}
        </button>
      </form>
    </div>

    <div class="card mt-6 p-6">
      <h2 class="text-lg font-semibold">Change email</h2>
      <p class="text-xs text-muted mt-1">
        We send a confirmation link to the new address. Until you click it, the
        current address stays active.
      </p>
      <form class="mt-3" @submit.prevent="changeEmail">
        <div class="field">
          <label class="label" for="email-new">New email</label>
          <input id="email-new" v-model="emailForm.new_email" type="email" class="input" required autocomplete="email" />
        </div>
        <div class="field">
          <label class="label" for="email-pw">Current password</label>
          <input id="email-pw" v-model="emailForm.current_password" type="password" class="input" required autocomplete="current-password" />
        </div>
        <button class="btn btn-primary" type="submit" :disabled="busy === 'email'">
          {{ busy === 'email' ? 'Sending…' : 'Send confirmation link' }}
        </button>
      </form>
    </div>

    <div class="card mt-6 p-6">
      <h2 class="text-lg font-semibold">Sessions</h2>
      <p class="text-xs text-muted mt-1">
        Signing out everywhere keeps this browser signed in with a fresh token.
      </p>
      <button class="btn btn-ghost mt-3" :disabled="busy === 'sessions'" @click="revokeOthers">
        {{ busy === 'sessions' ? 'Working…' : 'Sign out all other sessions' }}
      </button>
    </div>

    <div class="card mt-6 p-6">
      <h2 class="text-lg font-semibold text-down">Delete account</h2>
      <p class="text-sm text-muted mt-1">
        This anonymises your profile, disables the account and pauses your
        monitors. It cannot be undone.
      </p>
      <form class="mt-3" @submit.prevent="deleteAccount">
        <div class="field">
          <label class="label" for="del-pw">Current password</label>
          <input id="del-pw" v-model="deleteForm.current_password" type="password" class="input" required autocomplete="current-password" />
        </div>
        <div class="field">
          <label class="label" for="del-confirm">Type your username to confirm</label>
          <input id="del-confirm" v-model="deleteForm.confirmText" class="input" :placeholder="auth.user?.username" required />
        </div>
        <button class="btn btn-danger" type="submit" :disabled="busy === 'delete'">
          {{ busy === 'delete' ? 'Deleting…' : 'Delete my account' }}
        </button>
      </form>
    </div>
  </div>
</template>
