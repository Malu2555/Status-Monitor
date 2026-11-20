<script setup>
// Account security: opt-in TOTP two-factor authentication.
// Backend: /api/auth/otp/{status,enroll,activate,disable}.
import { onMounted, ref } from 'vue'
import * as authApi from '../api/auth'
import { logger } from '../utils/logger'

const enabled = ref(false)
const loading = ref(true)
const provisioningUri = ref('')
const code = ref('')
const busy = ref('')
const error = ref('')
const notice = ref('')

// API tokens
const tokens = ref([])
const tokenName = ref('')
const tokenScope = ref('write')
const newToken = ref('')
const tokenBusy = ref('')

// 2FA recovery codes
const recoveryCodes = ref([])
const recoverySummary = ref({ total: 0, unused: 0 })
const regenCode = ref('')
const recoveryBusy = ref('')

async function load() {
  loading.value = true
  try {
    enabled.value = (await authApi.otpStatus()).enabled
    if (enabled.value) await loadRecoverySummary()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadRecoverySummary() {
  try {
    recoverySummary.value = await authApi.getRecoveryCodes()
  } catch (e) {
    error.value = e.message
  }
}

async function startEnroll() {
  error.value = ''
  notice.value = ''
  busy.value = 'enroll'
  try {
    provisioningUri.value = (await authApi.otpEnroll()).provisioning_uri
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function activate() {
  error.value = ''
  notice.value = ''
  busy.value = 'activate'
  try {
    const result = await authApi.otpActivate(code.value.trim())
    recoveryCodes.value = result.recovery_codes || []
    provisioningUri.value = ''
    code.value = ''
    notice.value = 'Two-factor authentication enabled — save your recovery codes below.'
    await load()
    logger.info('2FA enabled')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function disable() {
  error.value = ''
  notice.value = ''
  busy.value = 'disable'
  try {
    await authApi.otpDisable(code.value.trim())
    code.value = ''
    recoveryCodes.value = []
    recoverySummary.value = { total: 0, unused: 0 }
    notice.value = 'Two-factor authentication disabled.'
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function loadTokens() {
  try {
    tokens.value = await authApi.listTokens()
  } catch (e) {
    error.value = e.message
  }
}

async function createToken() {
  error.value = ''
  newToken.value = ''
  tokenBusy.value = 'create'
  try {
    const created = await authApi.createToken({
      name: tokenName.value.trim() || 'API token',
      scope: tokenScope.value,
    })
    newToken.value = created.token
    tokenName.value = ''
    await loadTokens()
  } catch (e) {
    error.value = e.message
  } finally {
    tokenBusy.value = ''
  }
}

async function revokeToken(id) {
  error.value = ''
  tokenBusy.value = 'revoke-' + id
  try {
    await authApi.revokeToken(id)
    await loadTokens()
  } catch (e) {
    error.value = e.message
  } finally {
    tokenBusy.value = ''
  }
}

async function regenerate() {
  error.value = ''
  notice.value = ''
  recoveryBusy.value = 'regen'
  try {
    const result = await authApi.regenerateRecoveryCodes(regenCode.value.trim())
    recoveryCodes.value = result.recovery_codes || []
    regenCode.value = ''
    notice.value = 'New recovery codes generated — save them now.'
    await loadRecoverySummary()
  } catch (e) {
    error.value = e.message
  } finally {
    recoveryBusy.value = ''
  }
}

async function copyRecoveryCodes() {
  try {
    await navigator.clipboard.writeText(recoveryCodes.value.join('\n'))
  } catch {
    /* clipboard unavailable — the codes are visible and downloadable */
  }
}

function downloadRecoveryCodes() {
  const blob = new Blob([recoveryCodes.value.join('\n') + '\n'], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'status-monitor-recovery-codes.txt'
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
onMounted(loadTokens)
</script>

<template>
  <div class="container">
    <h1 class="text-2xl font-bold">Security</h1>
    <p class="text-sm text-muted mt-1">Protect your account with a second factor.</p>

    <div v-if="error" class="error-box mt-6">{{ error }}</div>
    <div v-if="notice" class="card bg-primary-soft mt-6 text-sm">{{ notice }}</div>

    <div class="card mt-6">
      <div class="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h2 class="text-lg font-semibold">Two-factor authentication (TOTP)</h2>
          <p class="text-sm text-muted mt-1">
            {{ enabled ? 'Enabled — a 6-digit code is required at login.' : 'Not enabled — add an authenticator app.' }}
          </p>
        </div>
        <span class="text-sm font-semibold" :class="enabled ? 'text-up' : 'text-muted'">
          {{ enabled ? 'On' : 'Off' }}
        </span>
      </div>

      <div v-if="loading" class="text-sm text-muted mt-4">Checking status…</div>

      <template v-else>
        <!-- Enrollment: show the otpauth URI, then confirm with a code. -->
        <div v-if="!enabled && provisioningUri" class="mt-4">
          <p class="text-sm text-muted">
            Add this account to your authenticator app (paste the URI into your app or
            its “manual entry” field), then enter the 6-digit code below.
          </p>
          <div class="field mt-3">
            <label class="label" for="otp-uri">Provisioning URI</label>
            <input id="otp-uri" class="input" :value="provisioningUri" readonly />
          </div>
          <div class="field">
            <label class="label" for="otp-code">6-digit code</label>
            <input id="otp-code" v-model="code" class="input" inputmode="numeric" maxlength="6" autocomplete="one-time-code" />
          </div>
          <button class="btn btn-primary" :disabled="busy === 'activate' || code.trim().length < 6" @click="activate">
            {{ busy === 'activate' ? 'Verifying…' : 'Enable 2FA' }}
          </button>
        </div>

        <!-- Enabled: allow disabling with a current code. -->
        <div v-else-if="enabled" class="mt-4">
          <div class="field">
            <label class="label" for="otp-disable-code">Current 6-digit code</label>
            <input id="otp-disable-code" v-model="code" class="input" inputmode="numeric" maxlength="6" autocomplete="one-time-code" />
          </div>
          <button class="btn btn-ghost" :disabled="busy === 'disable' || code.trim().length < 6" @click="disable">
            {{ busy === 'disable' ? 'Disabling…' : 'Disable 2FA' }}
          </button>

          <hr style="border: none; border-top: 1px solid rgba(148, 163, 184, 0.25); margin: 1rem 0" />
          <p class="text-sm text-muted">
            Recovery codes:
            <strong>{{ recoverySummary.unused }}</strong> of {{ recoverySummary.total }} unused.
          </p>
          <div class="field mt-2">
            <label class="label" for="regen-code">Generate new codes (requires a current 6-digit code)</label>
            <input id="regen-code" v-model="regenCode" class="input" inputmode="numeric" maxlength="6" autocomplete="one-time-code" />
          </div>
          <button class="btn btn-ghost" :disabled="recoveryBusy === 'regen' || regenCode.trim().length < 6" @click="regenerate">
            {{ recoveryBusy === 'regen' ? 'Generating…' : 'Regenerate recovery codes' }}
          </button>
        </div>

        <!-- Not enrolled yet. -->
        <div v-else class="mt-4">
          <button class="btn btn-primary" :disabled="busy === 'enroll'" @click="startEnroll">
            {{ busy === 'enroll' ? 'Preparing…' : 'Set up 2FA' }}
          </button>
        </div>
      </template>
    </div>

    <div v-if="recoveryCodes.length" class="card mt-6">
      <h2 class="text-lg font-semibold">Save your recovery codes</h2>
      <p class="text-sm text-muted mt-1">
        Each code works once if you lose access to your authenticator. They are shown
        only now, so store them somewhere safe.
      </p>
      <div class="card bg-primary-soft mt-3">
        <div class="flex flex-wrap gap-3 text-sm">
          <code v-for="c in recoveryCodes" :key="c">{{ c }}</code>
        </div>
      </div>
      <div class="flex gap-2 mt-3 flex-wrap">
        <button class="btn btn-ghost btn-sm" @click="copyRecoveryCodes">Copy all</button>
        <button class="btn btn-ghost btn-sm" @click="downloadRecoveryCodes">Download .txt</button>
        <button class="btn btn-primary btn-sm" @click="recoveryCodes = []">I saved them</button>
      </div>
    </div>

    <div class="card mt-6">
      <h2 class="text-lg font-semibold">Developer access (API tokens)</h2>
      <p class="text-sm text-muted mt-1">
        Use a token with the <code>X-API-Key</code> header to manage monitors
        programmatically. Read-only tokens can view but not change anything.
      </p>

      <div v-if="newToken" class="card bg-primary-soft mt-4 text-sm">
        <p class="font-medium">Copy this token now — it is shown only once:</p>
        <input class="input mt-2" :value="newToken" readonly />
      </div>

      <div class="flex flex-wrap gap-2 items-end mt-4">
        <div class="field flex-1" style="min-width: 180px">
          <label class="label" for="token-name">Name</label>
          <input id="token-name" v-model="tokenName" class="input" placeholder="CI deploy" />
        </div>
        <div class="field" style="min-width: 140px">
          <label class="label" for="token-scope">Scope</label>
          <select id="token-scope" v-model="tokenScope" class="input">
            <option value="write">Write</option>
            <option value="read">Read only</option>
          </select>
        </div>
        <button class="btn btn-primary" :disabled="tokenBusy === 'create'" @click="createToken">
          {{ tokenBusy === 'create' ? 'Creating…' : 'Create token' }}
        </button>
      </div>

      <div v-if="tokens.length === 0" class="text-sm text-muted mt-4">No tokens yet.</div>
      <ul v-else class="mt-4" style="list-style: none; padding: 0; margin: 0">
        <li
          v-for="t in tokens"
          :key="t.id"
          class="flex justify-between items-center gap-3 text-sm"
          style="padding: 0.5rem 0; border-top: 1px solid rgba(148, 163, 184, 0.25)"
        >
          <div>
            <strong>{{ t.name }}</strong>
            <span class="text-muted"> · {{ t.scope }} · {{ t.prefix }}…</span>
            <span v-if="t.revoked" class="text-muted"> · revoked</span>
          </div>
          <button
            v-if="!t.revoked"
            class="btn btn-ghost btn-sm"
            :disabled="tokenBusy === 'revoke-' + t.id"
            @click="revokeToken(t.id)"
          >
            {{ tokenBusy === 'revoke-' + t.id ? 'Revoking…' : 'Revoke' }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>