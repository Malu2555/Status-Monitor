<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppFooter from './components/AppFooter.vue'
import NavBar from './components/NavBar.vue'

const route = useRoute()
const flush = computed(() => Boolean(route.meta.landing))
</script>

<template>
  <NavBar />
  <main class="page" :class="{ 'page--landing': flush }">
    <router-view />
  </main>
  <AppFooter />
</template>
