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
      Status Monitor — free public status page · private dashboard · Stripe billing
    </p>
  </footer>
</template>
