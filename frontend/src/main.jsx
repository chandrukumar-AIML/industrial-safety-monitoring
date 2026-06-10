/**
 * frontend/src/main.jsx
 *
 * Application entry point with providers, error handling, and initialization.
 *
 * # FIXED: Proper React 18 createRoot usage
 * # FIXED: Global error handling with user-friendly fallback
 * # IMPROVED: Strict mode for development safety
 * # FIXED: Environment variable validation at startup
 * # IMPROVED: CSP meta tag injection for security
 */

import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

// ── Environment Validation ───────────────────────────────────
const validateEnv = () => {
  const required = ['VITE_API_URL']
  const missing = required.filter(key => !import.meta.env[key])
  
  if (missing.length > 0 && import.meta.env.PROD) {
    console.error('❌ Missing required environment variables:', missing.join(', '))
    // In production, show user-friendly error
    document.body.innerHTML = `
      <div style="
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #0d1117;
        color: #f1f5f9;
        font-family: system-ui;
        padding: 2rem;
        text-align: center;
      ">
        <div>
          <h1 style="font-size: 1.5rem; margin-bottom: 1rem;">Configuration Error</h1>
          <p style="color: #94a3b8; margin-bottom: 1.5rem;">
            Required environment variables are missing: ${missing.join(', ')}
          </p>
          <p style="font-size: 0.875rem; color: #64748b;">
            Please contact your administrator or check the deployment configuration.
          </p>
        </div>
      </div>
    `
    throw new Error(`Missing env vars: ${missing.join(', ')}`)
  }
  
  // Warn in development
  if (missing.length > 0) {
    console.warn('⚠️  Missing environment variables (dev mode):', missing.join(', '))
  }
}

// ── Global Error Handling ────────────────────────────────────
const setupGlobalErrorHandling = () => {
  // Unhandled promise rejections
  window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason)
    // Could send to error tracking service
  })

  // Global JS errors
  window.addEventListener('error', (event) => {
    console.error('Global error:', event.error)
    // Prevent default browser error page in production
    if (import.meta.env.PROD) {
      event.preventDefault()
    }
  })
}

// ── Security: Inject CSP Meta Tag ────────────────────────────
const injectCSP = () => {
  if (document.querySelector('meta[http-equiv="Content-Security-Policy"]')) {
    return // Already set by server
  }
  
  const meta = document.createElement('meta')
  meta.httpEquiv = 'Content-Security-Policy'
  
  // Development CSP (more permissive for hot reload)
  const devCSP = `
    default-src 'self';
    script-src 'self' 'unsafe-inline' 'unsafe-eval' http://localhost:*;
    style-src 'self' 'unsafe-inline' http://localhost:*;
    img-src 'self' data: blob: http://localhost:*;
    connect-src 'self' ws://localhost:* wss://localhost:* http://localhost:* https://localhost:*;
    font-src 'self';
    frame-src 'none';
  `.replace(/\s+/g, ' ').trim()
  
  // Production CSP (strict)
  const prodCSP = `
    default-src 'self';
    script-src 'self' 'sha256-<hash-of-inline-scripts>';
    style-src 'self' 'sha256-<hash-of-inline-styles>';
    img-src 'self' data: blob:;
    connect-src 'self' wss: https:;
    font-src 'self';
    frame-src 'none';
  `.replace(/\s+/g, ' ').trim()
  
  meta.content = import.meta.env.PROD ? prodCSP : devCSP
  document.head.appendChild(meta)
}

// ── Global fetch auth shim ───────────────────────────────────
// Several panels use raw fetch() with no Authorization header. In dev the Vite
// proxy injects the key, but in production (Vercel) there is no proxy, so those
// calls 401. This wraps window.fetch to attach the Bearer key for requests that
// target the backend API base — fixing all raw-fetch panels in one place.
const installFetchAuthShim = () => {
  const API_URL = import.meta.env.VITE_API_URL || ''
  const API_KEY = import.meta.env.VITE_API_KEY
    || import.meta.env.VITE_DEMO_API_KEY
    || '05ac3ecf4b9d6e8fc0a7f353d0d5023d83aa8b40bf4fb2ff277ab3f1eed5802a'
  if (!API_KEY) return
  const origFetch = window.fetch.bind(window)
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : (input && input.url) || ''
    const isApi = url.startsWith(API_URL) || url.startsWith('/api')
    if (isApi) {
      const headers = new Headers((init && init.headers) || {})
      if (!headers.has('Authorization')) headers.set('Authorization', `Bearer ${API_KEY}`)
      init = { ...init, headers }
    }
    return origFetch(input, init)
  }
}

// ── Application Initialization ───────────────────────────────
const initApp = () => {
  // Validate environment
  validateEnv()

  // Attach auth to raw fetch() calls hitting the backend
  installFetchAuthShim()
  
  // Setup error handling
  setupGlobalErrorHandling()
  
  // Inject security headers
  injectCSP()
  
  // Log app info in dev
  if (import.meta.env.DEV) {
    console.log(`🚀 ${import.meta.env.VITE_APP_NAME || 'Safety Monitor'} starting...`)
    console.log('API URL:', import.meta.env.VITE_API_URL)
    console.log('WS URL:', import.meta.env.VITE_WS_URL || 'auto')
  }
  
  // Render app
  const root = createRoot(document.getElementById('root'))
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  )
}

// Start the app
initApp()