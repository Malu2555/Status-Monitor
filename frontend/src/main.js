import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { initTheme } from './composables/useTheme'

// Self-hosted variable font (CSP-safe: no external font CDN).
import '@fontsource-variable/inter'

// CSS architecture: design tokens + reset → utilities (Tailwind-style) → components → landing
import './assets/css/main.css'
import './assets/css/utilities.css'
import './assets/css/components.css'
import './assets/css/landing.css'

// The inline script in index.html already applied the theme before first paint;
// this registers the live system-preference listener.
initTheme()

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')

