<script setup>
// Light sticky top bar for the app shell: title, refresh, theme, avatar menu.
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme'
import { useAuthStore } from '../stores/auth'
import AppIcon from './AppIcon.vue'

const auth = useAuthStore()
const router = useRouter()
const { preference, resolved, cycle } = useTheme()

const open = ref(false)
const wrapRef = ref(null)
const btnRef = ref(null)

const initials = computed(() => (auth.user?.username || '?').slice(0, 1).toUpperCase())
const themeIcon = computed(() =>
  preference.value === 'system' ? 'monitor' : resolved.value === 'dark' ? 'moon' : 'sun',
)
const themeLabel = computed(() => `Theme: ${preference.value}. Click to switch to the next theme.`)

function closeMenu(returnFocus = false) {
  if (!open.value) return
  open.value = false
  if (returnFocus) nextTick(() => btnRef.value?.focus())
}

function onDocumentClick(event) {
  if (open.value && wrapRef.value && !wrapRef.value.contains(event.target)) closeMenu()
}

function onKeydown(event) {
  if (event.key === 'Escape') closeMenu(true)
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})

function refresh() {
  window.location.reload()
}

async function onLogout() {
  closeMenu()
  await auth.logout()
  router.push({ name: 'home' })
}
</script>

<template>
  <header class="app-topbar">
    <div class="app-topbar__left">
      <h1 class="app-topbar__title">Status Monitor</h1>
      <router-link
        :to="{ name: 'home' }"
        class="btn btn-ghost btn-sm back-site"
        title="Go to the landing page"
      >
        <AppIcon name="globe" :size="16" />
        <span>Back to site</span>
      </router-link>
    </div>
    <div class="app-topbar__actions">
      <button type="button" class="topbar-icon" aria-label="Refresh" title="Refresh" @click="refresh">
        <AppIcon name="refresh" :size="18" />
      </button>
      <button
        type="button"
        class="topbar-icon"
        :aria-label="themeLabel"
        :title="themeLabel"
        @click="cycle"
      >
        <AppIcon :name="themeIcon" :size="18" />
      </button>

      <div ref="wrapRef" class="avatar-wrap">
        <button
          ref="btnRef"
          type="button"
          class="avatar-btn avatar-btn--light"
          :aria-expanded="open"
          aria-haspopup="menu"
          @click="open = !open"
        >
          <span class="avatar-circle">{{ initials }}</span>
          <span class="avatar-name truncate">{{ auth.user?.username }}</span>
          <span class="avatar-caret"><AppIcon name="chevron-down" :size="16" /></span>
        </button>

        <div v-if="open" class="avatar-menu" role="menu">
          <router-link
            :to="{ name: 'account' }"
            class="avatar-menu__item"
            role="menuitem"
            @click="closeMenu()"
          >
            <AppIcon name="user" :size="16" /> Your Profile
          </router-link>
          <router-link
            :to="{ name: 'notifications' }"
            class="avatar-menu__item"
            role="menuitem"
            @click="closeMenu()"
          >
            <AppIcon name="bell" :size="16" /> Notifications
          </router-link>
          <router-link
            :to="{ name: 'security' }"
            class="avatar-menu__item"
            role="menuitem"
            @click="closeMenu()"
          >
            <AppIcon name="lock" :size="16" /> Security
          </router-link>
          <div class="avatar-menu__divider"></div>
          <button type="button" class="avatar-menu__item" role="menuitem" @click="onLogout">
            <AppIcon name="x" :size="16" /> Log out
          </button>
        </div>
      </div>
    </div>
  </header>
</template>
