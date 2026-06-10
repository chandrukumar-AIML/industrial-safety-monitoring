/**
 * frontend/src/components/ExportButton.jsx
 *
 * Reusable export button for CSV/JSON downloads.
 * Triggers a GET request to the export endpoint and saves the file.
 *
 * Props:
 *   endpoint   — e.g. "/export/violations.csv"
 *   label      — button label (default: "Export CSV")
 *   params     — query params object (e.g. { zone_id: "zone-a", severity: "HIGH" })
 *   variant    — "csv" | "json" (controls icon)
 *   className  — additional Tailwind classes
 */

import { useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function ExportButton({
  endpoint,
  label,
  params = {},
  variant = 'csv',
  className = '',
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const icon = variant === 'json' ? '📋' : '⬇️'
  const defaultLabel = variant === 'json' ? 'Export JSON' : 'Export CSV'

  async function handleExport() {
    setLoading(true)
    setError(null)
    try {
      const url = new URL(`${API_BASE}${endpoint}`)
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') {
          url.searchParams.set(k, v)
        }
      })

      const res = await fetch(url.toString())
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(detail.detail || `Export failed: ${res.status}`)
      }

      const blob = await res.blob()
      const disposition = res.headers.get('Content-Disposition') || ''
      const filenameMatch = disposition.match(/filename="([^"]+)"/)
      const filename = filenameMatch ? filenameMatch[1] : `export_${Date.now()}.${variant}`

      const objectUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objectUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(objectUrl)
    } catch (err) {
      console.error('[ExportButton]', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <button
        onClick={handleExport}
        disabled={loading}
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium
                    bg-emerald-700/30 hover:bg-emerald-600/40 text-emerald-300
                    border border-emerald-700/50 disabled:opacity-50 disabled:cursor-not-allowed
                    transition-colors ${className}`}
      >
        {loading ? (
          <span className="animate-spin text-sm">⏳</span>
        ) : (
          <span>{icon}</span>
        )}
        {loading ? 'Exporting…' : (label || defaultLabel)}
      </button>
      {error && (
        <p className="text-xs text-red-400 mt-0.5">{error}</p>
      )}
    </div>
  )
}
