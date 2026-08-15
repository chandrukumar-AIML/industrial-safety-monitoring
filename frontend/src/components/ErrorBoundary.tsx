/**
 * frontend/src/components/ErrorBoundary.jsx
 *
 * React Error Boundary — catches unhandled JS errors in any child component
 * and shows a graceful fallback instead of crashing the entire dashboard.
 *
 * Role: Frontend Developer / QA Engineer
 *
 * Usage:
 *   <ErrorBoundary>
 *     <SomePanel />
 *   </ErrorBoundary>
 *
 * Features:
 *   - Per-panel isolation: one panel crash won't take down the whole app
 *   - Production-safe: hides stack traces in production
 *   - One-click retry to remount the component
 *   - Auto-reports errors to console (plug in Sentry here for production)
 */

import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
    }
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render shows the fallback UI
    return {
      hasError: true,
      error,
      errorId: `err-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    }
  }

  componentDidCatch(error, errorInfo) {
    // Log error details for debugging
    console.error('[ErrorBoundary] Caught error:', error)
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack)

    this.setState({ errorInfo })

    // ── Plug Sentry in here for production ────────────────
    // if (window.Sentry) {
    //   Sentry.captureException(error, { extra: errorInfo })
    // }
  }

  handleRetry = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
    })
  }

  render() {
    const { hasError, error, errorId } = this.state
    const { children, fallback, panelName } = this.props

    if (!hasError) return children

    // Custom fallback provided by parent
    if (fallback) return fallback

    const isProduction = import.meta.env.PROD
    const label = panelName || 'This panel'

    return (
      <div
        role="alert"
        style={{
          background: '#1e293b',
          border: '1px solid #dc2626',
          borderRadius: 10,
          padding: '24px 28px',
          fontFamily: 'system-ui, sans-serif',
          color: '#f1f5f9',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <span style={{ fontSize: 22 }}>⚠️</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: '#fca5a5' }}>
              {label} encountered an error
            </div>
            <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
              Error ID: {errorId}
            </div>
          </div>
        </div>

        {/* Message */}
        <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16, lineHeight: 1.6 }}>
          This panel crashed and has been isolated to prevent affecting the rest
          of the dashboard. The other tabs are still working normally.
        </p>

        {/* Error details (dev only) */}
        {!isProduction && error && (
          <details style={{ marginBottom: 16 }}>
            <summary
              style={{
                fontSize: 12,
                color: '#64748b',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              Show error details (dev only)
            </summary>
            <pre
              style={{
                marginTop: 8,
                background: '#0f172a',
                borderRadius: 6,
                padding: '10px 14px',
                fontSize: 11,
                color: '#f87171',
                overflow: 'auto',
                maxHeight: 200,
              }}
            >
              {error.toString()}
              {'\n\n'}
              {this.state.errorInfo?.componentStack}
            </pre>
          </details>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={this.handleRetry}
            style={{
              background: '#2563eb',
              border: 'none',
              borderRadius: 6,
              color: '#fff',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600,
              padding: '8px 16px',
            }}
          >
            🔄 Retry
          </button>
          <button
            onClick={() => window.location.reload()}
            style={{
              background: '#334155',
              border: 'none',
              borderRadius: 6,
              color: '#94a3b8',
              cursor: 'pointer',
              fontSize: 13,
              padding: '8px 16px',
            }}
          >
            ↺ Reload page
          </button>
        </div>
      </div>
    )
  }
}
