import { defineStore } from 'pinia'
import * as authApi from '../api/auth'
import * as billingApi from '../api/billing'
import { setAccessToken, setOnUnauthorized } from '../api/client'
import { logger } from '../utils/logger'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null, // { id, username, email, plan, plan_label, monitors_used, monitors_limit, subscription_status }
    accessToken: null, // kept ONLY in memory — never localStorage
    ready: false,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken),
  },

  actions: {
    setSession(data) {
      this.accessToken = data.access
      setAccessToken(data.access)
      this.user = data.user
      this.ready = true
    },

    clear() {
      this.accessToken = null
      this.user = null
      setAccessToken(null)
    },

    async bootstrap() {
      // Called once at app start: /me will 401 without a token, which triggers
      // the client's silent refresh (refresh cookie) — or we end up logged out.
      setOnUnauthorized(() => this.clear())
      try {
        const data = await authApi.me()
        this.user = data
        logger.info('session restored for', data.username)
      } catch (error) {
        if (error.status !== 401) logger.warn('session bootstrap failed', error.message)
        this.clear()
      } finally {
        this.ready = true
      }
    },

    async login(username, password) {
      logger.info('logging in', username)
      this.setSession(await authApi.login({ username, password }))
    },

    async register(payload) {
      logger.info('registering', payload.username)
      this.setSession(await authApi.register(payload))
    },

    async logout() {
      try {
        await authApi.logout()
      } finally {
        logger.info('logged out')
        this.clear()
      }
    },

    async refreshBilling() {
      if (!this.accessToken || !this.user) return
      this.user = { ...this.user, ...(await billingApi.summary()) }
    },
  },
})
