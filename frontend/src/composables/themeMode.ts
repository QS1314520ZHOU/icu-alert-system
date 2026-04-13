import { readonly, ref } from 'vue'

export type ThemeMode = 'dark' | 'light'

const THEME_KEY = 'icu_theme_mode'

function readThemeMode(): ThemeMode {
  if (typeof document !== 'undefined') {
    const attr = document.documentElement.getAttribute('data-theme')
    if (attr === 'light' || attr === 'dark') return attr
  }
  if (typeof window !== 'undefined') {
    const saved = window.localStorage.getItem(THEME_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  }
  return 'dark'
}

const themeModeState = ref<ThemeMode>(readThemeMode())

function syncThemeMode(mode?: ThemeMode) {
  themeModeState.value = mode || readThemeMode()
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === THEME_KEY) syncThemeMode()
  })

  window.addEventListener('icu-theme-change', ((event: Event) => {
    const detail = (event as CustomEvent<{ mode?: ThemeMode }>).detail
    syncThemeMode(detail?.mode)
  }) as EventListener)
}

export function setThemeMode(mode: ThemeMode) {
  syncThemeMode(mode)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('icu-theme-change', { detail: { mode } }))
  }
}

export function useThemeMode() {
  return readonly(themeModeState)
}

export function getThemeMode() {
  return themeModeState.value
}
