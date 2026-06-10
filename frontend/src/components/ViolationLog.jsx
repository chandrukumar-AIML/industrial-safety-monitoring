// src/components/ViolationLog.jsx
import { useState, memo, useCallback } from 'react'
import { format, isValid }             from 'date-fns'
import PropTypes                       from 'prop-types'
import { CheckCircle, Eye, AlertTriangle, ClipboardList } from 'lucide-react'
import { useViolations, useAcknowledge }  from '../hooks/useViolations'
import { SHAPModal }                      from './SHAPModal'
import { LOG_FILTERS }                    from '../constants'

const CLASS_COLORS = {
  'no helmet'  : 'bg-red-500/15 text-red-400 border-red-500/30',
  'no vest'    : 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  'no hardhat' : 'bg-red-500/15 text-red-400 border-red-500/30',
  'no gloves'  : 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  'no goggles' : 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  'no boots'   : 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  'no mask'    : 'bg-pink-500/15 text-pink-400 border-pink-500/30',
  'no suit'    : 'bg-rose-500/15 text-rose-400 border-rose-500/30',
}

const FILTERS = LOG_FILTERS

const ViolationRow = memo(function ViolationRow({ v, onExplain, onAck }) {
  let time = '—'
  if (v.timestamp) {
    const ts = new Date(v.timestamp)
    if (isValid(ts)) time = format(ts, 'HH:mm:ss')
  }
  return (
    <tr className={`border-b border-slate-800/40 hover:bg-slate-800/20
                    transition-colors text-xs ${v.acknowledged ? 'opacity-40' : ''}`}>
      <td className="px-3 py-2 text-slate-500 font-mono whitespace-nowrap">{time}</td>
      <td className="px-3 py-2">
        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs
          border ${CLASS_COLORS[v.class_name] ?? 'bg-slate-800 text-slate-400 border-slate-700'}`}>
          {v.class_name}
        </span>
      </td>
      <td className="px-3 py-2 text-slate-400 font-mono">
        {(v.confidence * 100).toFixed(0)}%
      </td>
      <td className="px-3 py-2 text-slate-500">{v.zone_id ?? '—'}</td>
      <td className="px-3 py-2 text-slate-600 font-mono">#{v.track_id}</td>
      <td className="px-3 py-2">
        <div className="flex gap-2 items-center">
          <button
            title="Explain (SHAP)"
            onClick={() => onExplain(v)}
            className="text-slate-600 hover:text-blue-400 transition-colors"
            aria-label={`SHAP explanation for track ${v.track_id}`}
          >
            <Eye size={12}/>
          </button>
          {!v.acknowledged && (
            <button
              title="Acknowledge"
              onClick={() => onAck({ id: v.id })}
              className="text-slate-600 hover:text-green-400 transition-colors"
              aria-label={`Acknowledge violation ${v.id}`}
            >
              <CheckCircle size={12}/>
            </button>
          )}
        </div>
      </td>
    </tr>
  )
})

ViolationRow.propTypes = {
  v: PropTypes.shape({
    id          : PropTypes.number.isRequired,
    track_id    : PropTypes.number.isRequired,
    class_name  : PropTypes.string.isRequired,
    confidence  : PropTypes.number.isRequired,
    zone_id     : PropTypes.string,
    timestamp   : PropTypes.string,
    acknowledged: PropTypes.bool.isRequired,
  }).isRequired,
  onExplain: PropTypes.func.isRequired,
  onAck    : PropTypes.func.isRequired,
}

export function ViolationLog() {
  const [filter,     setFilter]     = useState('all')
  const [shapTarget, setShapTarget] = useState(null)

  const {
    data: raw = [],
    isLoading,
    isError,
  } = useViolations({
    limit      : 100,
    class_name : filter === 'all' || filter === 'unacked' ? undefined : filter,
    acknowledged: filter === 'unacked' ? false : undefined,
  })

  const violations = Array.isArray(raw) ? raw : raw?.data || raw?.violations || []
  const { mutate: ack } = useAcknowledge()

  const handleExplain = useCallback((v) => setShapTarget(v), [])
  const handleAck     = useCallback((args) => ack(args), [ack])

  return (
    <div className="bg-[#0d1117] border border-slate-800/60 rounded-xl
                    flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5
                      border-b border-slate-800/50 shrink-0">
        <div className="flex items-center gap-2">
          <ClipboardList size={13} className="text-slate-500"/>
          <span className="font-medium text-xs text-slate-300">Violation Log</span>
          {violations.length > 0 && (
            <span className="text-xs bg-slate-800 text-slate-400 px-1.5 py-0.5
                             rounded-md tabular-nums">
              {violations.length}
            </span>
          )}
        </div>
        <div className="flex gap-1" role="group" aria-label="Filter violations">
          {FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              aria-pressed={filter === f}
              className={`px-2.5 py-0.5 rounded-md text-xs transition-colors ${
                filter === f
                  ? 'bg-orange-500/20 border border-orange-500/40 text-orange-300'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-y-auto flex-1 text-xs">
        {isLoading && (
          <p className="text-slate-600 p-4 text-center">Loading…</p>
        )}

        {isError && !isLoading && (
          <div className="flex flex-col items-center justify-center
                          p-8 gap-2 text-red-400/70">
            <AlertTriangle size={18}/>
            <p className="text-sm">Failed to load violations</p>
          </div>
        )}

        {!isLoading && !isError && violations.length === 0 && (
          <p className="text-slate-700 p-6 text-center">No violations</p>
        )}

        {!isLoading && !isError && violations.length > 0 && (
          <table className="w-full">
            <thead className="sticky top-0 bg-[#0d1117]/95
                              text-slate-600 border-b border-slate-800/50">
              <tr>
                {['Time','Class','Conf','Zone','Track',''].map(h => (
                  <th key={h} className="text-left px-3 py-2 font-normal text-xs
                                         tracking-wider uppercase text-slate-700">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {violations.map(v => (
                <ViolationRow
                  key={v.id}
                  v={v}
                  onExplain={handleExplain}
                  onAck={handleAck}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {shapTarget && (
        <SHAPModal
          violation={shapTarget}
          onClose={() => setShapTarget(null)}
        />
      )}
    </div>
  )
}

export default ViolationLog
