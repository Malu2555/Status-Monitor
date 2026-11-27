<script setup>
// Top navigation: marketing links + CTA for visitors, app links when signed in.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme'
import { useAuthStore } from '../stores/auth'
import AppIcon from './AppIcon.vue'
import AppLogo from './AppLogo.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { preference, resolved, cycle } = useTheme()
const menuOpen = ref(false)
const headerRef = ref(null)
const toggleRef = ref(null)
const menuRef = ref(null)

const isAppMode = computed(() => Boolean(route.meta.requiresAuth) || auth.isAuthenticated)
const themeIcon = computed(() =>
  preference.value === 'system' ? 'monitor' : resolved.value === 'dark' ? 'moon' : 'sun',
)
const themeLabel = computed(
  () => `Theme: ${preference.value}. Click to switch to the next theme.`,
)
const marketingLinks = [
  { label: 'Features', hash: '#features' },
  { label: 'Use Cases', hash: '#use-cases' },
  { label: 'Status Pages', hash: '#status-pages' },
  { label: 'Integrations', hash: '#integrations' },
  { label: 'Pricing', hash: '#pricing' },
]

function closeMenu(returnFocus = false) {
  if (!menuOpen.value) return
  menuOpen.value = false
  if (returnFocus) nextTick(() => toggleRef.value?.focus())
}

function onDocumentClick(event) {
  if (menuOpen.value && headerRef.value && !headerRef.value.contains(event.target)) {
    closeMenu()
  }
}

function onKeydown(event) {
  if (event.key === 'Escape') closeMenu(true)
}

function onResize() {
  if (window.innerWidth > 960) closeMenu()
}

watch(
  () => route.fullPath,
  () => closeMenu(),
)

watch(menuOpen, async (open) => {
  document.body.classList.toggle('menu-open', open)
  if (open) {
    await nextTick()
    menuRef.value?.focus()
  }
})

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onResize)
  document.body.classList.remove('menu-open')
})

async function onLogout() {
  await auth.logout()
  router.push({ name: 'home' })
}
</script>

<template>
  <header ref="headerRef" class="navbar">
    <div class="navbar-inner">
      <router-link :to="{ name: 'home' }" class="brand" @click="menuOpen = false">
        <AppLogo :size="28" />
        <span>Status Monitor</span>
      </router-link>

      <nav class="nav-links" aria-label="Main">
        <template v-if="isAppMode">
          <router-link :to="{ name: 'dashboard' }" class="nav-link">Dashboard</router-link>
          <router-link :to="{ name: 'notifications' }" class="nav-link">Alerts</router-link>
          <router-link :to="{ name: 'maintenance' }" class="nav-link">Maintenance</router-link>
          <router-link :to="{ name: 'statuspages' }" class="nav-link">Status Pages</router-link>
          <router-link :to="{ name: 'security' }" class="nav-link">Security</router-link>
          <router-link :to="{ name: 'account' }" class="nav-link">Account</router-link>
        </template>
        <template v-else>
          <router-link
            v-for="link in marketingLinks"
            :key="link.hash"
            :to="{ name: 'home', hash: link.hash }"
            class="nav-link"
          >
            {{ link.label }}
          </router-link>
          <router-link v-if="!auth.isAuthenticated" :to="{ name: 'login' }" class="nav-link">
            Login
          </router-link>
        </template>
      </nav>

      <div class="nav-actions">
        <button
          type="button"
          class="theme-toggle"
          :aria-label="themeLabel"
          :title="themeLabel"
          @click="cycle"
        >
          <AppIcon :name="themeIcon" :size="18" />
        </button>
        <template v-if="auth.isAuthenticated">
          <button class="btn btn-ghost btn-sm" @click="onLogout">Log out</button>
        </template>
        <template v-else>
          <router-link :to="{ name: 'register' }" class="btn btn-primary nav-cta">
            Start Monitoring Free
          </router-link>
        </template>
        <button
          ref="toggleRef"
          class="nav-toggle"
          type="button"
          :aria-expanded="menuOpen"
          aria-controls="mobile-menu"
          aria-label="Toggle navigation"
          @click="menuOpen = !menuOpen"
        >
          <AppIcon :name="menuOpen ? 'x' : 'menu'" :size="20" />
        </button>
      </div>

      <div
        id="mobile-menu"
        ref="menuRef"
        class="mobile-menu"
        :class="{ 'is-open': menuOpen }"
        tabindex="-1"
      >
        <button
          type="button"
          class="btn btn-ghost mobile-theme-btn"
          :aria-label="themeLabel"
          @click="cycle"
        >
          <AppIcon :name="themeIcon" :size="18" />
          Theme: {{ preference }}
        </button>
        <template v-if="isAppMode">
          <router-link :to="{ name: 'dashboard' }" class="nav-link">Dashboard</router-link>
          <router-link :to="{ name: 'notifications' }" class="nav-link">Alerts</router-link>
          <router-link :to="{ name: 'maintenance' }" class="nav-link">Maintenance</router-link>
          <router-link :to="{ name: 'statuspages' }" class="nav-link">Status Pages</router-link>
          <router-link :to="{ name: 'security' }" class="nav-link">Security</router-link>
          <router-link :to="{ name: 'account' }" class="nav-link">Account</router-link>
          <div class="mobile-menu-actions">
            <button class="btn btn-ghost" @click="onLogout">Log out</button>
          </div>
        </template>
        <template v-else>
          <router-link
            v-for="link in marketingLinks"
            :key="link.hash"
            :to="{ name: 'home', hash: link.hash }"
            class="nav-link"
          >
            {{ link.label }}
          </router-link>
          <router-link v-if="!auth.isAuthenticated" :to="{ name: 'login' }" class="nav-link">
            Login
          </router-link>
          <div v-if="!auth.isAuthenticated" class="mobile-menu-actions">
            <router-link :to="{ name: 'register' }" class="btn btn-primary">
              Start Monitoring Free
            </router-link>
          </div>
        </template>
      </div>
    </div>
  </header>
</template>
