/**
 * Toast.jsx
 * Lightweight toast notification system — no dependencies.
 *
 * Why: the app previously used native alert() (17 call sites) which blocks the
 * thread, looks unprofessional, and can't be styled. This provides non-blocking,
 * themed, auto-dismissing notifications.
 *
 * Usage:
 *   const toast = useToast()
 *   toast.success('Permit approved')
 *   toast.error('Could not reach server')
 */
import { createContext, useContext, useState, useCallback, useRef } from 'react'

const ToastContext = createContext(null)

const MAX_VISIBLE = 3
const AUTO_DISMISS_MS = 3000   // success/info/warning auto-close; errors stay

const STYLES = {
  success: { bar: 'bg-emerald-500', icon: '✓', ring: 'border-emerald-500/40', text: 'text-emerald-300' },
  error:   { bar: 'bg-red-500',     icon: '✕', ring: 'border-red-500/40',     text: 'text-red-300' },
  warning: { bar: 'bg-amber-500',   icon: '!', ring: 'border-amber-500/40',   text: 'text-amber-300' },
  info:    { bar: 'bg-brand-500',   icon: 'i', ring: 'border-brand-500/40',   text: 'text-brand-300' },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const push = useCallback((type, message) => {
    const id = ++idRef.current
    setToasts(prev => {
      const next = [...prev, { id, type, message }]
      // Keep only the most recent MAX_VISIBLE
      return next.slice(-MAX_VISIBLE)
    })
    // Errors persist until dismissed; everything else auto-closes
    if (type !== 'error') {
      setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
    }
    return id
  }, [dismiss])

  const api = {
    success: (m) => push('success', m),
    error:   (m) => push('error', m),
    warning: (m) => push('warning', m),
    info:    (m) => push('info', m),
    dismiss,
  }

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* Container — fixed top-right, above everything */}
      <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none">
        {toasts.map(t => {
          const s = STYLES[t.type] || STYLES.info
          return (
            <div
              key={t.id}
              role="status"
              aria-live="polite"
              className={`pointer-events-auto flex items-start gap-3 bg-surface-raised border ${s.ring}
                          rounded-xl shadow-lg shadow-black/30 overflow-hidden animate-[slideIn_0.2s_ease-out]`}
            >
              <div className={`w-1.5 self-stretch ${s.bar}`} />
              <div className={`flex items-center justify-center w-6 h-6 mt-3 rounded-full ${s.bar} text-slate-900 text-xs font-bold shrink-0`}>
                {s.icon}
              </div>
              <p className="flex-1 py-3 text-sm text-slate-200 leading-snug">{t.message}</p>
              <button
                onClick={() => dismiss(t.id)}
                className="px-3 py-3 text-slate-500 hover:text-slate-200 transition-colors shrink-0"
                aria-label="Dismiss"
              >
                ✕
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    // Fallback so a missing provider never crashes a panel
    return {
      success: (m) => console.log('[toast:success]', m),
      error:   (m) => console.error('[toast:error]', m),
      warning: (m) => console.warn('[toast:warning]', m),
      info:    (m) => console.info('[toast:info]', m),
      dismiss: () => {},
    }
  }
  return ctx
}

export default ToastProvider
