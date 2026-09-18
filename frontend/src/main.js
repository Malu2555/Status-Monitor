import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

// CSS architecture: design tokens + reset → utilities (Tailwind-style) → components
import './assets/css/main.css'
import './assets/css/utilities.css'
import './assets/css/components.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')

