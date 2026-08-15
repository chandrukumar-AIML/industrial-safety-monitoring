/**
 * frontend/src/components/AuditLogPanel.jsx
 *
 * Audit log viewer — shows all safety-critical actions in chronological order.
 * Required for OSHA & ISO 45001 compliance.
 *
 * Features:
 *   - Filter by action type, actor, date range
 *   - Action badges color-coded by severity
 *   - Paginated
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ACTION_COLORS = {
  'violation.acknowledged': 'bg-emerald-900/40 text-emerald-400',
  'violation.unacknowledged': 'bg-amber-900/40 text-amber-400',
  'worker.deleted': 'bg-red-900/40 text-red-400',
  'worker.created': 'bg-blue-900/40 text-blue-400',
  'worker.face_enrolled': 'bg-purple-900/40 text-purple-400',
  'webhook.deleted': 'bg-red-900/40 text-red-400',
  'apikey.revoked': 'bg-red-900/40 text-red-400',
  'apikey.created': 'bg-blue-900/40 text-blue-400',
  'export.downloaded': 'bg-slate-700 text-slate-300',
  'report.generated': 'bg-indigo-900/40 text-indigo-400',
  'system.startup': 'bg-emerald-900/30 text-emerald-500',
}

function actionBadge(action) {
  const cls = ACTION_COLORS[action] || 'bg-slate-800 text-slate-400'
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-mono ${cls}`}>
      {action}
    </span>
  )
}

async function fetchAudit(params) {
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')
  const url = `${API_BASE}/audit${qs ? '?' + qs : ''}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return Array.isArray(data) ? data : []
}

const PAGE_SIZE = 25

export default function AuditLogPanel() {
  const [page, setPage] = useState(0)
  const [filters, setFilters] = useState({ action: '', actor: '', start_date: '', end_date: '' })
  const [pendingFilters, setPending] = useState(filters)

  const { data = [], isLoading, isError } = useQuery({
    queryKey: ['audit', filters, page],
    queryFn: () => fetchAudit({
      ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    keepPreviousData: true,
  })

  function applyFilters(e) {
    e.preventDefault()
    setFilters(pendingFilters)
    setPage(0)
  }

  function clearFilters() {
    const empty = { action: '', actor: '', start_date: '', end_date: '' }
    setFilters(empty)
    setPending(empty)
    setPage(0)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">📋 Audit Log</h2>
          <p className="text-xs text-slate-500 mt-0.5">OSHA / ISO 45001 compliance — all safety actions recorded</p>
        </div>
      </div>

      {/* Filters */}
      <form onSubmit={applyFilters} className="bg-slate-800/40 rounded-lg p-3 border border-slate-700/40">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <input
            className="bg-slate-900/60 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
            placeholder="Action type…"
            value={pendingFilters.action}
            onChange={e => setPending(f => ({ ...f, action: e.target.value }))}
          />
          <input
            className="bg-slate-900/60 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
            placeholder="Actor (user/system)…"
            value={pendingFilters.actor}
            onChange={e => setPending(f => ({ ...f, actor: e.target.value }))}
          />
          <input
            type="date"
            className="bg-slate-900/60 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
            value={pendingFilters.start_date}
            onChange={e => setPending(f => ({ ...f, start_date: e.target.value }))}
          />
          <input
            type="date"
            className="bg-slate-900/60 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
            value={pendingFilters.end_date}
            onChange={e => setPending(f => ({ ...f, end_date: e.target.value }))}
          />
        </div>
        <div className="flex gap-2 mt-2">
          <button type="submit" className="px-3 py-1 bg-brand-500 hover:bg-brand-600 text-slate-900 font-semibold text-xs rounded transition-colors">
            Apply
          </button>
          <button type="button" onClick={clearFilters} className="px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors">
            Clear
          </button>
        </div>
      </form>

      {/* Table */}
      {isLoading ? (
        <div className="text-slate-400 text-sm text-center py-8">Loading audit log…</div>
      ) : isError ? (
        <div className="text-red-400 text-sm text-center py-8">
          Failed to load audit log. You may need Manager or Admin role.
        </div>
      ) : data.length === 0 ? (
        <div className="text-slate-500 text-sm text-center py-8 border border-dashed border-slate-700 rounded-lg">
          No audit entries found for these filters.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-800/60 text-slate-500">
                <th className="text-left py-2 pr-4 font-medium">Action</th>
                <th className="text-left py-2 pr-4 font-medium">Actor</th>
                <th className="text-left py-2 pr-4 font-medium">Resource</th>
                <th className="text-left py-2 pr-4 font-medium">Time</th>
                <th className="text-left py-2 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {data.map(entry => (
                <tr key={entry.id} className="hover:bg-slate-800/20 transition-colors">
                  <td className="py-2.5 pr-4">{actionBadge(entry.action)}</td>
                  <td className="py-2.5 pr-4 text-slate-300">{entry.actor}</td>
                  <td className="py-2.5 pr-4 text-slate-500">
                    {entry.resource_type && (
                      <span>{entry.resource_type}{entry.resource_id ? ` #${entry.resource_id}` : ''}</span>
                    )}
                  </td>
                  <td className="py-2.5 pr-4 text-slate-500 whitespace-nowrap">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="py-2.5 text-slate-600 max-w-xs truncate">
                    {entry.details ? (
                      <span title={JSON.stringify(entry.details)}>
                        {typeof entry.details === 'object'
                          ? Object.entries(entry.details).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(', ')
                          : String(entry.details).slice(0, 60)
                        }
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {data.length > 0 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>Page {page + 1}</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 rounded transition-colors"
            >
              ← Prev
            </button>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={data.length < PAGE_SIZE}
              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 rounded transition-colors"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
