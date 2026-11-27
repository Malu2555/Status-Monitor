<script setup>
// Left navigation for the authenticated app shell (dark in both themes).
import { useRoute } from 'vue-router'
import AppIcon from './AppIcon.vue'
import AppLogo from './AppLogo.vue'

const route = useRoute()

const primary = [
  { label: 'Home', icon: 'home', to: { name: 'dashboard' }, match: ['dashboard'] },
  { label: 'Monitors', icon: 'monitor', to: { name: 'monitors' }, match: ['monitors', 'monitor'] },
  { label: 'Status Pages', icon: 'window', to: { name: 'statuspages' }, match: ['statuspages'] },
]
const settings = {
  label: 'Settings',
  icon: 'settings',
  to: { name: 'account' },
  match: ['account', 'security', 'notifications', 'maintenance'],
}

function isActive(item) {
  return item.match.includes(route.name)
}
</script>

<template>
  <aside class="app-sidebar">
    <router-link :to="{ name: 'dashboard' }" class="sidebar-brand">
      <AppLogo :size="30" with-wordmark />
    </router-link>

    <nav class="sidebar-nav" aria-label="Primary">
      <router-link
        v-for="item in primary"
        :key="item.label"
        :to="item.to"
        class="sidebar-item"
        :class="{ 'is-active': isActive(item) }"
      >
        <AppIcon :name="item.icon" :size="20" />
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

    <div class="sidebar-footer">
      <router-link
        :to="settings.to"
        class="sidebar-item"
        :class="{ 'is-active': isActive(settings) }"
      >
        <AppIcon :name="settings.icon" :size="20" />
        <span>{{ settings.label }}</span>
      </router-link>
    </div>
  </aside>
</template>
