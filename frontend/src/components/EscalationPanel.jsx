/**
 * EscalationPanel.jsx
 *
 * Alert Escalation Matrix — shows all open L1→L4 alerts.
 * Red badges for L3/L4, acknowledge button per alert.
 */
import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '../api/client'
import { useToast } from './Toast'

const LEVEL_STYLES = {
  1: { label: 'L1 Supervisor',       bg: 'bg-yellow-500/15', text: 'text-yellow-300', border: 'border-yellow-500/30' },
  2: { label: 'L2 Safety Officer',   bg: 'bg-orange-500/15', text: 'text-orange-300', border: 'border-orange-500/30' },
  3: { label: 'L3 Plant Head',       bg: 'bg-red-500/15',    text: 'text-red-300',    border: 'border-red-500/30' },
  4: { label: 'L4 EMERGENCY',        bg: 'bg-red-900/40',    text: 'text-red-200',    border: 'border-red-400/60' },
}

function AckModal({ alert, onClose, onAck }) {
  const [name, setName] = useState('')
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-80">
        <h3 className="text-white font-bold mb-3">Acknowledge Alert #{alert.id}</h3>
        <p className="text-gray-400 text-sm mb-4">
          Violation: <span className="text-white">{alert.class_name || 'N/A'}</span><br />
          Zone: <span className="text-white">{alert.zone_id || 'N/A'}</span>
        </p>
        <input
          className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm mb-4"
          placeholder="Your name / badge ID"
          value={name}
          onChange={e => setName(e.target.value)}
          autoFocus
        />
        <div className="flex gap-2">
          <button
            disabled={!name.trim()}
            onClick={() => onAck(alert.id, name)}
            className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-40 text-white rounded-lg py-2 text-sm font-medium"
          >
            Acknowledge
          </button>
          <button
            onClick={onClose}
            className="flex-1 bg-gray-700 hover:bg-gray-600 text-white rounded-lg py-2 text-sm"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

export default function EscalationPanel() {
  const toast = useToast()
  const [alerts, setAlerts] = useState([])
  const [stats, setStats] = useState({})
  const [loading, setLoading] = useState(true)
  const [ackModal, setAckModal] = useState(null)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const [alertsRes, statsRes] = await Promise.all([
        apiClient.get('/escalation/open'),
        apiClient.get('/escalation/stats/summary'),
      ])
      setAlerts(alertsRes.data.alerts || [])
      setStats(statsRes.data)
      setError(null)
    } catch (e) {
      setError('Failed to load escalation data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 30000)
    return () => clearInterval(id)
  }, [fetchData])

  const handleAck = async (escalationId, name) => {
    try {
      await apiClient.post(`/escalation/acknowledge/${escalationId}`, {
        acknowledged_by: name,
      })
      setAckModal(null)
      fetchData()
      toast.success('Alert acknowledged')
    } catch (e) {
      toast.error('Could not acknowledge the alert. Try again.')
    }
  }

  const criticalCount = alerts.filter(a => a.level >= 3).length
  const totalOpen = alerts.length

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 p-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">🚨</span>
          <h2 className="text-white font-bold text-lg">Alert Escalation</h2>
          {criticalCount > 0 && (
            <span className="bg-red-600 text-white text-xs font-bold px-2 py-0.5 rounded-full animate-pulse">
              {criticalCount} CRITICAL
            </span>
          )}
        </div>
        <div className="flex gap-3 text-xs text-gray-400">
          <span>Open: <span className="text-white font-medium">{totalOpen}</span></span>
          <span>Total: <span className="text-white font-medium">{stats.total || 0}</span></span>
        </div>
      </div>

      {/* Level legend */}
      <div className="grid grid-cols-4 gap-1 mb-4">
        {[1, 2, 3, 4].map(l => {
          const s = LEVEL_STYLES[l]
          const count = stats.by_status
            ? Object.values(stats.by_level?.[String(l)] || {}).reduce((a, b) => a + b, 0)
            : 0
          return (
            <div key={l} className={`${s.bg} border ${s.border} rounded-lg p-2 text-center`}>
              <div className={`${s.text} font-bold text-sm`}>L{l}</div>
              <div className="text-gray-400 text-xs">{count}</div>
            </div>
          )
        })}
      </div>

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {loading && (
          <div className="text-gray-500 text-sm text-center py-8">Loading alerts…</div>
        )}
        {!loading && error && (
          <div className="text-red-400 text-sm text-center py-4">{error}</div>
        )}
        {!loading && !error && alerts.length === 0 && (
          <div className="text-gray-500 text-sm text-center py-8">
            <div className="text-3xl mb-2">✅</div>
            No open escalations
          </div>
        )}
        {alerts.map(alert => {
          const s = LEVEL_STYLES[alert.level] || LEVEL_STYLES[1]
          return (
            <div
              key={alert.id}
              className={`${s.bg} border ${s.border} rounded-lg p-3 flex items-start justify-between gap-2`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`${s.text} font-bold text-xs`}>{s.label}</span>
                  {alert.level === 4 && (
                    <span className="bg-red-600 text-white text-xs px-1 rounded animate-pulse">EMERGENCY</span>
                  )}
                </div>
                <div className="text-white text-sm font-medium truncate">
                  {alert.class_name || 'PPE Violation'} — {alert.zone_id || 'Unknown Zone'}
                </div>
                <div className="text-gray-400 text-xs mt-0.5">
                  Violation #{alert.violation_id} •{' '}
                  {alert.minutes_open != null ? `${alert.minutes_open}m open` : 'Just triggered'}
                  {alert.org_id && ` • ${alert.org_id}`}
                </div>
                {alert.escalation_reason && (
                  <div className="text-orange-400 text-xs mt-1">⚠ {alert.escalation_reason}</div>
                )}
              </div>
              <button
                onClick={() => setAckModal(alert)}
                className="bg-green-700 hover:bg-green-600 text-white text-xs px-3 py-1.5 rounded-lg whitespace-nowrap"
              >
                Acknowledge
              </button>
            </div>
          )
        })}
      </div>

      {ackModal && (
        <AckModal
          alert={ackModal}
          onClose={() => setAckModal(null)}
          onAck={handleAck}
        />
      )}
    </div>
  )
}
