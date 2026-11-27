<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppFooter from './components/AppFooter.vue'
import AppHeader from './components/AppHeader.vue'
import NavBar from './components/NavBar.vue'

const route = useRoute()
const flush = computed(() => Boolean(route.meta.landing))
// Authenticated pages get the dark app chrome; public/marketing pages keep the
// light marketing navbar and site footer.
const isApp = computed(() => Boolean(route.meta.requiresAuth))
</script>

<template>
  <AppHeader v-if="isApp" />
  <NavBar v-else />
  <main class="page" :class="{ 'page--landing': flush }">
    <router-view />
  </main>
  <AppFooter v-if="!isApp" />
</template>

