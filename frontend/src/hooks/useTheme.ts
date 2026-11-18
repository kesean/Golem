import { useState, useEffect } from 'react'

export type Theme = 'light' | 'dark'

// Mirrored by the inline script in index.html, which applies the class before paint.
export function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem('theme')
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // Storage blocked (private mode, disabled site data): use the OS preference
  }
  const prefersDark =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  return prefersDark ? 'dark' : 'light'
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  // Only an explicit toggle is stored. The OS-derived default is never written,
  // so it keeps following the OS.
  const toggle = () => {
    const next: Theme = theme === 'light' ? 'dark' : 'light'
    setTheme(next)
    try {
      localStorage.setItem('theme', next)
    } catch {
      // Not persisted; the toggle still works for this page view
    }
  }

  return { theme, toggle }
}
