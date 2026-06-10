/**
 * PermitPanel.jsx
 *
 * Digital Permit-to-Work management.
 * Request, approve, validate, close permits.
 */
import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '../api/client'
import { useToast } from './Toast'

const WORK_TYPE_ICONS = {
  hot_work: '🔥', confined_space: '🕳️', electrical: '⚡',
  height_work: '🏗️', chemical: '☣️', excavation: '⛏️',
  radiation: '☢️', cold_work: '🔧', general: '📋',
}

const STATUS_STYLES = {
  pending:   'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  active:    'bg-green-500/15 text-green-300 border-green-500/30',
  expired:   'bg-red-500/15 text-red-300 border-red-500/30',
  cancelled: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  closed:    'bg-blue-500/15 text-blue-300 border-blue-500/30',
}

const WORK_TYPES = [
  'hot_work', 'confined_space', 'electrical', 'height_work',
  'chemical', 'excavation', 'radiation', 'cold_work', 'general',
]

function RequestForm({ onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({ work_type: 'hot_work', worker_id: '', zone_id: '', supervisor_id: '' })
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (!form.worker_id.trim()) return
    setLoading(true)
    try {
      const res = await apiClient.post('/permits', {
        work_type: form.work_type,
        worker_id: form.worker_id.trim() || undefined,
        zone_id: form.zone_id.trim() || undefined,
        supervisor_id: form.supervisor_id.trim() || undefined,
      })
      onCreated?.(res.data)
      setForm({ work_type: 'hot_work', worker_id: '', zone_id: '', supervisor_id: '' })
      toast.success('Permit request submitted')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to request permit')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 mb-4">
      <h3 className="text-white font-medium text-sm mb-3">Request New Permit</h3>
      <div className="grid grid-cols-2 gap-2 mb-2">
        <select
          value={form.work_type}
          onChange={e => setForm(f => ({ ...f, work_type: e.target.value }))}
          className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm col-span-2"
        >
          {WORK_TYPES.map(wt => (
            <option key={wt} value={wt}>
              {WORK_TYPE_ICONS[wt]} {wt.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            </option>
          ))}
        </select>
        <input
          className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
          placeholder="Worker ID"
          value={form.worker_id}
          onChange={e => setForm(f => ({ ...f, worker_id: e.target.value }))}
        />
        <input
          className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
          placeholder="Zone ID"
          value={form.zone_id}
          onChange={e => setForm(f => ({ ...f, zone_id: e.target.value }))}
        />
      </div>
      <button
        onClick={submit}
        disabled={loading || !form.worker_id.trim()}
        className="w-full bg-orange-600 hover:bg-orange-700 disabled:opacity-40 text-white rounded-lg py-2 text-sm font-medium"
      >
        📋 Submit Permit Request
      </button>
    </div>
  )
}

function PermitCard({ permit, onRefresh }) {
  const toast = useToast()
  const [approving, setApproving] = useState(false)
  const [approver, setApprover] = useState('')
  const [showApprove, setShowApprove] = useState(false)
  const style = STATUS_STYLES[permit.status] || STATUS_STYLES.pending
  const icon = WORK_TYPE_ICONS[permit.work_type] || '📋'

  const handleApprove = async () => {
    if (!approver.trim()) return
    setApproving(true)
    try {
      await apiClient.post(`/permits/${permit.permit_id}/approve`, {
        approved_by: approver,
        valid_hours: 8,
      })
      setShowApprove(false)
      onRefresh?.()
      toast.success(`Permit ${permit.permit_id} approved`)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Approval failed')
    } finally {
      setApproving(false)
    }
  }

  const handleClose = async () => {
    try {
      await apiClient.post(`/permits/${permit.permit_id}/close`)
      onRefresh?.()
      toast.success('Permit closed')
    } catch (e) {
      toast.error('Could not close permit. Try again.')
    }
  }

  const handleCancel = async () => {
    try {
      await apiClient.post(`/permits/${permit.permit_id}/cancel`)
      onRefresh?.()
      toast.info('Permit cancelled')
    } catch (e) {
      toast.error('Could not cancel permit. Try again.')
    }
  }

  return (
    <div className={`border rounded-xl p-3 mb-2 ${style}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span>{icon}</span>
            <span className="text-white font-medium text-sm">
              {permit.work_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${style}`}>
              {permit.status}
            </span>
          </div>
          <div className="text-xs text-gray-400">
            {permit.permit_id} • Worker: {permit.worker_id || '—'} • Zone: {permit.zone_id || '—'}
          </div>
          {permit.valid_until && (
            <div className="text-xs text-gray-500 mt-0.5">
              Valid until: {new Date(permit.valid_until).toLocaleString()}
            </div>
          )}
          {permit.qr_code && (
            <div className="text-xs text-green-500 mt-0.5">QR: {permit.qr_code.slice(0, 30)}…</div>
          )}
        </div>
        <div className="flex flex-col gap-1">
          {permit.status === 'pending' && (
            <button
              onClick={() => setShowApprove(s => !s)}
              className="bg-green-700 hover:bg-green-600 text-white text-xs px-2 py-1 rounded"
            >
              Approve
            </button>
          )}
          {permit.status === 'active' && (
            <button
              onClick={handleClose}
              className="bg-surface-high hover:bg-slate-600 text-slate-200 text-xs px-2 py-1 rounded"
            >
              Close
            </button>
          )}
          {['pending', 'active'].includes(permit.status) && (
            <button
              onClick={handleCancel}
              className="bg-gray-700 hover:bg-gray-600 text-white text-xs px-2 py-1 rounded"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
      {showApprove && (
        <div className="mt-2 flex gap-2">
          <input
            className="flex-1 bg-gray-900 border border-gray-600 rounded px-2 py-1 text-white text-xs"
            placeholder="Approver name"
            value={approver}
            onChange={e => setApprover(e.target.value)}
            autoFocus
          />
          <button
            disabled={approving || !approver.trim()}
            onClick={handleApprove}
            className="bg-green-600 hover:bg-green-700 disabled:opacity-40 text-white text-xs px-3 py-1 rounded"
          >
            Confirm
          </button>
        </div>
      )}
    </div>
  )
}

export default function PermitPanel() {
  const [permits, setPermits] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  const fetchPermits = useCallback(async () => {
    try {
      const params = filter !== 'all' ? `?status=${filter}` : ''
      const res = await apiClient.get(`/permits${params}`)
      setPermits(res.data.permits || [])
    } catch (e) {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    fetchPermits()
  }, [fetchPermits])

  const counts = permits.reduce((acc, p) => {
    acc[p.status] = (acc[p.status] || 0) + 1
    return acc
  }, {})

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">📋</span>
          <h2 className="text-white font-bold text-lg">Permit to Work</h2>
        </div>
        <div className="flex gap-1 text-xs">
          {['all', 'pending', 'active', 'expired'].map(s => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-2 py-1 rounded capitalize ${filter === s ? 'bg-orange-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
            >
              {s} {s !== 'all' && counts[s] ? `(${counts[s]})` : ''}
            </button>
          ))}
        </div>
      </div>

      {/* Summary chips */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {[
          { k: 'pending', icon: '⏳', color: 'yellow' },
          { k: 'active',  icon: '✅', color: 'green' },
          { k: 'expired', icon: '⌛', color: 'red' },
          { k: 'closed',  icon: '✔️', color: 'blue' },
        ].map(({ k, icon, color }) => (
          <div key={k} className={`bg-${color}-500/10 border border-${color}-500/30 rounded-xl p-2 text-center`}>
            <div className="text-lg">{icon}</div>
            <div className={`text-${color}-400 font-bold`}>{counts[k] || 0}</div>
            <div className="text-gray-500 text-xs capitalize">{k}</div>
          </div>
        ))}
      </div>

      <RequestForm onCreated={fetchPermits} />

      <div className="flex-1 overflow-y-auto">
        {loading && <div className="text-gray-500 text-sm text-center py-4">Loading…</div>}
        {!loading && permits.length === 0 && (
          <div className="text-gray-600 text-sm text-center py-8">
            No permits found. Submit one above.
          </div>
        )}
        {permits.map(p => (
          <PermitCard key={p.permit_id} permit={p} onRefresh={fetchPermits} />
        ))}
      </div>
    </div>
  )
}
