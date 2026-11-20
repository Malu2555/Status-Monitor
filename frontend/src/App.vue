<script setup>
import NavBar from './components/NavBar.vue'

</script>

<template>
  <NavBar />
  <main class="page">
    <router-view />
  </main>
  <footer class="footer">
    <p class="text-xs text-muted">
      Status Monitor · open-source uptime &amp; status pages · billing by Polar
    </p>
    <p class="text-xs text-muted mt-1">
      <router-link :to="{ name: 'terms' }">Terms of Service</router-link>
      ·
      <router-link :to="{ name: 'privacy' }">Privacy Policy</router-link>
    </p>
  </footer>
</template>
