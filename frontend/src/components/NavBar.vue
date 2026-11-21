<script setup>
// Top navigation: brand, public page link, auth-aware actions.
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function onLogout() {
  await auth.logout()
  router.push({ name: 'public' })
}
</script>

<template>
  <header class="navbar">
    <div class="navbar-inner">
      <router-link :to="{ name: 'public' }" class="brand">📡 Status Monitor</router-link>
      <nav class="flex items-center gap-1">
        <router-link :to="{ name: 'public' }" class="nav-link">Status</router-link>
        <template v-if="auth.isAuthenticated">
          <router-link :to="{ name: 'dashboard' }" class="nav-link">Dashboard</router-link>
          <router-link :to="{ name: 'notifications' }" class="nav-link">Alerts</router-link>
          <router-link :to="{ name: 'maintenance' }" class="nav-link">Maintenance</router-link>
          <router-link :to="{ name: 'statuspages' }" class="nav-link">Status pages</router-link>
          <router-link :to="{ name: 'security' }" class="nav-link">Security</router-link>
          <router-link :to="{ name: 'account' }" class="nav-link">{{ auth.user?.username }}</router-link>
          <button class="btn btn-ghost btn-sm" @click="onLogout">Log out</button>
        </template>
        <template v-else>
          <router-link :to="{ name: 'login' }" class="nav-link">Log in</router-link>
          <router-link :to="{ name: 'register' }" class="btn btn-primary btn-sm">Get started</router-link>
        </template>
      </nav>
    </div>
  </header>
</template>
