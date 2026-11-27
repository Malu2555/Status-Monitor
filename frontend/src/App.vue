<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppFooter from './components/AppFooter.vue'
import AppSidebar from './components/AppSidebar.vue'
import AppTopBar from './components/AppTopBar.vue'
import NavBar from './components/NavBar.vue'

const route = useRoute()
const flush = computed(() => Boolean(route.meta.landing))
// Authenticated pages use the left-sidebar app shell; public/marketing pages
// keep the light navbar and site footer.
const isApp = computed(() => Boolean(route.meta.requiresAuth))
</script>

<template>
  <div v-if="isApp" class="app-shell">
    <AppSidebar />
    <div class="app-body">
      <AppTopBar />
      <main class="app-main">
        <router-view />
      </main>
    </div>
  </div>
  <template v-else>
    <NavBar />
    <main class="page" :class="{ 'page--landing': flush }">
      <router-view />
    </main>
    <AppFooter />
  </template>
</template>


