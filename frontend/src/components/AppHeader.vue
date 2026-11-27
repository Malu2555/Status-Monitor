<script setup>
// Authenticated app header (dark navy in both themes): brand, Monitors/Status
// Pages tabs, theme toggle, and an avatar dropdown (profile / notifications /
// security / log out).
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme'
import { useAuthStore } from '../stores/auth'
import AppIcon from './AppIcon.vue'
import AppLogo from './AppLogo.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { preference, resolved, cycle } = useTheme()

const open = ref(false)
const wrapRef = ref(null)
const btnRef = ref(null)

const tabs = [
  { name: 'dashboard', label: 'Monitors' },
  { name: 'statuspages', label: 'Status Pages' },
]

// Keep "Monitors" highlighted while on a monitor's detail page too.
function isTabActive(name) {
  if (name === 'dashboard') return ['dashboard', 'monitor'].includes(route.name)
  return route.name === name
}

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

async function onLogout() {
  closeMenu()
  await auth.logout()
  router.push({ name: 'home' })
}
</script>

<template>
  <header class="app-header">
    <div class="app-header__inner">
      <router-link :to="{ name: 'dashboard' }" class="app-header__brand">
        <AppLogo :size="28" with-wordmark />
      </router-link>

      <nav class="app-header__tabs" aria-label="Primary">
        <router-link
          v-for="t in tabs"
          :key="t.name"
          :to="{ name: t.name }"
          class="app-tab"
          :class="{ 'router-link-active': isTabActive(t.name) }"
        >
          {{ t.label }}
        </router-link>
      </nav>

      <span class="app-header__spacer"></span>

      <div class="app-header__actions">
        <button
          type="button"
          class="theme-toggle"
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
            class="avatar-btn"
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
    </div>
  </header>
</template>
