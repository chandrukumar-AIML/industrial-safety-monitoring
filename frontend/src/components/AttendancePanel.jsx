/**
 * AttendancePanel.jsx
 *
 * Real-time worker headcount, check-in/out, and muster drill.
 * Shows on-site workers per site with hours on site.
 */
import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '../api/client'

function CheckInForm({ onSuccess }) {
  const [workerId, setWorkerId] = useState('')
  const [siteId, setSiteId] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  const submit = async (type) => {
    if (!workerId.trim()) return
    setLoading(true)
    setMsg(null)
    try {
      if (type === 'in') {
        await apiClient.post('/attendance/checkin', {
          worker_id: workerId.trim(),
          site_id: siteId.trim() || undefined,
          entry_method: 'manual',
        })
        setMsg({ ok: true, text: `${workerId} checked IN ✅` })
      } else {
        await apiClient.post('/attendance/checkout', {
          worker_id: workerId.trim(),
        })
        setMsg({ ok: true, text: `${workerId} checked OUT ✅` })
      }
      setWorkerId('')
      onSuccess?.()
    } catch (e) {
      setMsg({ ok: false, text: e.response?.data?.detail || 'Error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 mb-4">
      <h3 className="text-white font-medium text-sm mb-3">Manual Check-In / Check-Out</h3>
      <div className="flex gap-2 mb-2">
        <input
          className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
          placeholder="Worker ID / Badge"
          value={workerId}
          onChange={e => setWorkerId(e.target.value)}
        />
        <input
          className="w-32 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
          placeholder="Site ID"
          value={siteId}
          onChange={e => setSiteId(e.target.value)}
        />
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => submit('in')}
          disabled={loading || !workerId.trim()}
          className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-40 text-white rounded-lg py-2 text-sm font-medium"
        >
          ✅ Check In
        </button>
        <button
          onClick={() => submit('out')}
          disabled={loading || !workerId.trim()}
          className="flex-1 bg-surface-high hover:bg-slate-600 disabled:opacity-40 text-slate-200 rounded-lg py-2 text-sm font-medium"
        >
          🚪 Check Out
        </button>
      </div>
      {msg && (
        <div className={`mt-2 text-xs px-2 py-1 rounded ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>
          {msg.text}
        </div>
      )}
    </div>
  )
}

export default function AttendancePanel() {
  const [headcount, setHeadcount] = useState({ total_on_site: 0, by_site: [] })
  const [activeWorkers, setActiveWorkers] = useState([])
  const [musterResult, setMusterResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [musterLoading, setMusterLoading] = useState(false)
  const [todayStats, setTodayStats] = useState({})

  const fetchData = useCallback(async () => {
    try {
      const [hc, active, today] = await Promise.all([
        apiClient.get('/attendance/headcount'),
        apiClient.get('/attendance/active'),
        apiClient.get('/attendance/today'),
      ])
      setHeadcount(hc.data)
      setActiveWorkers(active.data.workers_on_site || [])
      setTodayStats(today.data)
    } catch (e) {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 15000)
    return () => clearInterval(id)
  }, [fetchData])

  const runMuster = async () => {
    setMusterLoading(true)
    try {
      const res = await apiClient.post('/attendance/muster')
      setMusterResult(res.data)
    } catch (e) {
      // ignore
    } finally {
      setMusterLoading(false)
    }
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 p-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">👷</span>
          <h2 className="text-white font-bold text-lg">Attendance & Headcount</h2>
        </div>
        <button
          onClick={runMuster}
          disabled={musterLoading}
          className="bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded-lg"
        >
          🚨 MUSTER DRILL
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-3 text-center">
          <div className="text-green-400 text-2xl font-bold">{headcount.total_on_site}</div>
          <div className="text-gray-400 text-xs mt-0.5">On Site</div>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-3 text-center">
          <div className="text-blue-400 text-2xl font-bold">{todayStats.total_checked_in || 0}</div>
          <div className="text-gray-400 text-xs mt-0.5">Today Check-ins</div>
        </div>
        <div className="bg-gray-500/10 border border-gray-500/30 rounded-xl p-3 text-center">
          <div className="text-gray-300 text-2xl font-bold">{todayStats.total_checked_out || 0}</div>
          <div className="text-gray-400 text-xs mt-0.5">Checked Out</div>
        </div>
      </div>

      {/* Check-in form */}
      <CheckInForm onSuccess={fetchData} />

      {/* Muster result */}
      {musterResult && (
        <div className="bg-red-900/30 border border-red-500/40 rounded-xl p-4 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-red-400 font-bold">🚨 MUSTER COMPLETE</span>
            <span className="text-white font-bold text-lg">{musterResult.total_on_site} workers</span>
          </div>
          <div className="text-gray-400 text-xs">{musterResult.muster_time}</div>
        </div>
      )}

      {/* Active workers list */}
      <div className="flex-1 overflow-y-auto">
        <div className="text-gray-400 text-xs font-medium mb-2 uppercase tracking-wide">
          Currently On-Site ({activeWorkers.length})
        </div>
        {loading && <div className="text-gray-500 text-sm py-4 text-center">Loading…</div>}
        {!loading && activeWorkers.length === 0 && (
          <div className="text-gray-600 text-sm py-4 text-center">No workers currently on site</div>
        )}
        <div className="space-y-1.5">
          {activeWorkers.map((w, i) => (
            <div
              key={i}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 flex items-center justify-between"
            >
              <div>
                <div className="text-white text-sm font-medium">
                  {w.full_name || w.worker_id}
                </div>
                <div className="text-gray-400 text-xs">
                  {w.worker_id} • {w.department || 'N/A'} • {w.site_id || 'Unknown site'}
                </div>
              </div>
              <div className="text-right">
                <div className="text-green-400 text-sm font-medium">
                  {w.hours_on_site != null ? `${w.hours_on_site}h` : '—'}
                </div>
                <div className="text-gray-500 text-xs">{w.entry_method}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
