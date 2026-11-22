// Light/dark preference: system by default, with an explicit override.
// The same palette tokens are used everywhere; only <html data-theme> changes.
import { computed, ref } from 'vue'

const STORAGE_KEY = 'sm-theme'
const OPTIONS = ['system', 'light', 'dark']
const meta =
  typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null

function readPreference() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return OPTIONS.includes(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

const preference = ref(readPreference())
const systemDark = ref(Boolean(meta?.matches))
const resolved = computed(() =>
  preference.value === 'system' ? (systemDark.value ? 'dark' : 'light') : preference.value,
)

function apply() {
  if (typeof document === 'undefined') return
  const theme = resolved.value
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
  const colorMeta = document.querySelector('meta[name="theme-color"]')
  if (colorMeta) colorMeta.setAttribute('content', theme === 'dark' ? '#0b1220' : '#10b981')
}

function setPreference(next) {
  if (!OPTIONS.includes(next)) return
  preference.value = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* storage can be unavailable (private mode) — the session still works */
  }
  apply()
}

let initialized = false

export function initTheme() {
  if (initialized) return
  initialized = true
  meta?.addEventListener?.('change', (event) => {
    systemDark.value = event.matches
    if (preference.value === 'system') apply()
  })
  apply()
}

export function useTheme() {
  initTheme()
  return {
    preference,
    resolved,
    setPreference,
    cycle() {
      const index = OPTIONS.indexOf(preference.value)
      setPreference(OPTIONS[(index + 1) % OPTIONS.length])
    },
  }
}
