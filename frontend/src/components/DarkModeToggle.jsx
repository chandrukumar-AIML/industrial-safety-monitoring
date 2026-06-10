/**
 * frontend/src/components/DarkModeToggle.jsx
 *
 * Dark / Light mode toggle.
 * Persists preference to localStorage (not sessionStorage — preference is not a secret).
 * Adds/removes "dark" class on <html> element for Tailwind dark: variant support.
 */

import { useEffect, useState } from 'react'

const STORAGE_KEY = 'sm_dark_mode'

function applyTheme(dark) {
  if (dark) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

export default function DarkModeToggle() {
  const [dark, setDark] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored !== null) return stored === 'true'
      // Default: prefer system setting
      return window.matchMedia('(prefers-color-scheme: dark)').matches
    } catch {
      return true  // Default dark
    }
  })

  useEffect(() => {
    applyTheme(dark)
    try {
      localStorage.setItem(STORAGE_KEY, String(dark))
    } catch {}
  }, [dark])

  return (
    <button
      onClick={() => setDark(d => !d)}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs
                 bg-slate-800/60 hover:bg-slate-700/60 text-slate-300
                 border border-slate-700/50 transition-colors"
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <span className="text-base">{dark ? '☀️' : '🌙'}</span>
      <span className="hidden lg:block">{dark ? 'Light' : 'Dark'}</span>
    </button>
  )
}
