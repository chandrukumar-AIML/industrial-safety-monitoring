/**
 * frontend/src/components/WebhookConfigPanel.jsx
 *
 * Webhook management UI — list, create, test, and delete outbound webhooks.
 *
 * Integrates with:
 *   POST   /webhooks       — create
 *   GET    /webhooks       — list
 *   DELETE /webhooks/{id}  — delete
 *   POST   /webhooks/{id}/test — test delivery
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const VALID_EVENTS = [
  'violation.critical', 'violation.high', 'fire.emergency',
  'fire.all_clear', 'worker.high_risk', 'weekly.report', 'drift.detected',
]

const WEBHOOK_TYPES = ['custom', 'slack', 'teams', 'jira']

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return null
  return res.json()
}

const defaultForm = {
  name: '',
  url: 'https://',
  webhook_type: 'custom',
  events: ['violation.critical', 'fire.emergency'],
  secret: '',
  active: true,
}

export default function WebhookConfigPanel() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(defaultForm)
  const [testResults, setTestResults] = useState({})
  const [formError, setFormError] = useState('')

  const { data: webhooks = [], isLoading } = useQuery({
    queryKey: ['webhooks'],
    queryFn: () => apiFetch('/webhooks'),
  })

  const createMut = useMutation({
    mutationFn: (body) => apiFetch('/webhooks', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
      setShowForm(false)
      setForm(defaultForm)
      setFormError('')
    },
    onError: (err) => setFormError(err.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id) => apiFetch(`/webhooks/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['webhooks'] }),
  })

  async function handleTest(id) {
    try {
      const result = await apiFetch(`/webhooks/${id}/test`, { method: 'POST' })
      setTestResults(r => ({ ...r, [id]: result }))
    } catch (err) {
      setTestResults(r => ({ ...r, [id]: { success: false, error: err.message } }))
    }
  }

  function toggleEvent(event) {
    setForm(f => ({
      ...f,
      events: f.events.includes(event)
        ? f.events.filter(e => e !== event)
        : [...f.events, event],
    }))
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (!form.name.trim()) { setFormError('Name is required'); return }
    if (!form.url.startsWith('https://')) { setFormError('URL must use HTTPS'); return }
    if (form.events.length === 0) { setFormError('Select at least one event'); return }
    setFormError('')
    createMut.mutate({
      name: form.name,
      url: form.url,
      webhook_type: form.webhook_type,
      events: form.events,
      secret: form.secret || undefined,
      active: form.active,
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">🔗 Outbound Webhooks</h2>
        <button
          onClick={() => setShowForm(v => !v)}
          className="px-3 py-1.5 bg-brand-500 hover:bg-brand-600 text-slate-900 font-semibold text-sm rounded-md transition-colors"
        >
          {showForm ? '✕ Cancel' : '+ Add Webhook'}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="bg-slate-800/60 rounded-lg p-4 space-y-3 border border-slate-700/50">
          <h3 className="text-sm font-semibold text-slate-300">New Webhook</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Name *</label>
              <input
                className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
                placeholder="Slack Safety Alerts"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                required
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Type</label>
              <select
                className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
                value={form.webhook_type}
                onChange={e => setForm(f => ({ ...f, webhook_type: e.target.value }))}
              >
                {WEBHOOK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">URL * (HTTPS required)</label>
            <input
              className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
              placeholder="https://hooks.slack.com/services/..."
              value={form.url}
              onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              required
            />
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Secret (for HMAC signing, optional)</label>
            <input
              type="password"
              className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
              placeholder="••••••••"
              value={form.secret}
              onChange={e => setForm(f => ({ ...f, secret: e.target.value }))}
            />
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Subscribe to events *</label>
            <div className="flex flex-wrap gap-2 mt-1">
              {VALID_EVENTS.map(ev => (
                <label key={ev} className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.events.includes(ev)}
                    onChange={() => toggleEvent(ev)}
                    className="accent-blue-500"
                  />
                  <span className="text-xs text-slate-300">{ev}</span>
                </label>
              ))}
            </div>
          </div>

          {formError && (
            <p className="text-xs text-red-400">{formError}</p>
          )}

          <button
            type="submit"
            disabled={createMut.isPending}
            className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm rounded-md transition-colors"
          >
            {createMut.isPending ? 'Creating…' : 'Create Webhook'}
          </button>
        </form>
      )}

      {/* Webhook list */}
      {isLoading ? (
        <div className="text-slate-400 text-sm">Loading webhooks…</div>
      ) : webhooks.length === 0 ? (
        <div className="text-slate-500 text-sm text-center py-8 border border-dashed border-slate-700 rounded-lg">
          No webhooks registered yet. Add one to forward safety alerts to Slack, Teams, or your custom endpoint.
        </div>
      ) : (
        <div className="space-y-3">
          {webhooks.map(wh => {
            const testResult = testResults[wh.id]
            return (
              <div key={wh.id} className="bg-slate-800/60 rounded-lg p-4 border border-slate-700/50">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm text-slate-200">{wh.name}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${wh.active ? 'bg-emerald-900/50 text-emerald-400' : 'bg-slate-700 text-slate-400'}`}>
                        {wh.active ? 'Active' : 'Inactive'}
                      </span>
                      <span className="text-xs bg-slate-700/60 text-slate-400 px-1.5 py-0.5 rounded">
                        {wh.webhook_type}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1 truncate">{wh.url}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {(wh.events || []).map(ev => (
                        <span key={ev} className="text-xs bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded">
                          {ev}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <button
                      onClick={() => handleTest(wh.id)}
                      className="px-2.5 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors"
                    >
                      🧪 Test
                    </button>
                    <button
                      onClick={() => deleteMut.mutate(wh.id)}
                      disabled={deleteMut.isPending}
                      className="px-2.5 py-1 bg-red-900/40 hover:bg-red-800/50 text-red-400 text-xs rounded transition-colors disabled:opacity-50"
                    >
                      🗑️
                    </button>
                  </div>
                </div>

                {/* Test result */}
                {testResult && (
                  <div className={`mt-3 text-xs p-2 rounded ${testResult.success ? 'bg-emerald-900/30 text-emerald-400' : 'bg-red-900/30 text-red-400'}`}>
                    {testResult.success
                      ? `✅ Delivered! Status: ${testResult.status_code} | Attempts: ${testResult.attempts}`
                      : `❌ Failed: ${testResult.error || `HTTP ${testResult.status_code}`}`
                    }
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
