<script setup>
// Global dark footer: brand, marketing links and legal/social row.
import AppIcon from './AppIcon.vue'
import AppLogo from './AppLogo.vue'

const year = new Date().getFullYear()
const repoUrl = 'https://github.com/Malu2555/Status-Monitor'
</script>

<template>
  <footer class="site-footer">
    <div class="footer-inner">
      <router-link :to="{ name: 'home' }" class="footer-brand">
        <AppLogo :size="30" />
        <span>Status Monitor</span>
      </router-link>

      <nav class="footer-nav" aria-label="Footer">
        <div class="footer-col">
          <p class="footer-col-title">Product <AppIcon name="chevron-down" :size="14" /></p>
          <router-link :to="{ name: 'home', hash: '#features' }">Features</router-link>
          <router-link :to="{ name: 'home', hash: '#use-cases' }">Use cases</router-link>
          <router-link :to="{ name: 'home', hash: '#status-pages' }">Status pages</router-link>
          <router-link :to="{ name: 'home', hash: '#pricing' }">Pricing</router-link>
        </div>
        <div class="footer-col">
          <p class="footer-col-title">Resources <AppIcon name="chevron-down" :size="14" /></p>
          <router-link :to="{ name: 'status' }">Live status</router-link>
          <router-link :to="{ name: 'home', hash: '#integrations' }">Integrations</router-link>
          <router-link :to="{ name: 'login' }">Log in</router-link>
        </div>
        <div class="footer-col">
          <p class="footer-col-title">Company <AppIcon name="chevron-down" :size="14" /></p>
          <router-link :to="{ name: 'terms' }">Terms of Service</router-link>
          <router-link :to="{ name: 'privacy' }">Privacy Policy</router-link>
        </div>
      </nav>

      <div class="footer-meta">
        <span>© {{ year }} Status Monitor</span>
        <span class="social-links">
          <a
            class="social-link"
            :href="repoUrl"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Status Monitor on GitHub"
          >
            <AppIcon name="github" :size="17" />
          </a>
          <router-link
            class="social-link"
            :to="{ name: 'home', hash: '#pricing' }"
            aria-label="Pricing"
          >
            <AppIcon name="spark" :size="17" />
          </router-link>
        </span>
      </div>
    </div>
  </footer>
</template>
