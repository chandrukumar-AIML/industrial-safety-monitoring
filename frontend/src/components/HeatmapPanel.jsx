// src/components/HeatmapPanel.jsx
import { useState } from 'react'
import { useHeatmap }   from '../hooks/useHeatmap'
import { resetHeatmap } from '../api/client'
import { RefreshCw, AlertTriangle, Flame, Activity } from 'lucide-react'

const RISK_STYLES = {
  low     : 'text-green-400  bg-green-500/10  border-green-500/25',
  medium  : 'text-yellow-400 bg-yellow-500/10 border-yellow-500/25',
  high    : 'text-orange-400 bg-orange-500/10 border-orange-500/25',
  critical: 'text-red-400    bg-red-500/10    border-red-500/30',
}

export function HeatmapPanel() {
  const { imgSrc, meta, error } = useHeatmap(3_000)   // poll every 3s for more responsiveness
  const [resetting,  setResetting]  = useState(false)
  const [resetError, setResetError] = useState(null)

  const handleReset = async () => {
    setResetting(true)
    setResetError(null)
    try {
      await resetHeatmap()
    } catch {
      setResetError('Reset failed — try again')
    } finally {
      setResetting(false)
    }
  }

  const frameCount = Number(meta?.frame_count ?? meta?.stats?.frame_count ?? 0)

  return (
    <div className="bg-[#0d1117] border border-slate-800/60 rounded-xl
                    p-4 flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Flame size={13} className="text-slate-500"/>
          <span className="font-medium text-xs text-slate-300">Zone Risk Heatmap</span>
          {frameCount > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-slate-600">
              <Activity size={9}/>
              {frameCount.toLocaleString()} frames
            </span>
          )}
        </div>
        <button
          onClick={handleReset}
          disabled={resetting}
          title="Reset accumulator"
          aria-label="Reset heatmap accumulator"
          className="text-slate-600 hover:text-slate-300 transition-colors
                     disabled:opacity-40 disabled:cursor-not-allowed p-1
                     rounded hover:bg-slate-800"
        >
          <RefreshCw size={12} className={resetting ? 'animate-spin' : ''}/>
        </button>
      </div>

      {resetError && (
        <p className="text-red-400/80 text-xs">{resetError}</p>
      )}

      {/* Heatmap image */}
      {error && !imgSrc ? (
        <div className="aspect-video bg-slate-900/50 border border-slate-800/40
                        rounded-lg flex flex-col items-center justify-center
                        gap-2 text-red-400/60">
          <AlertTriangle size={18}/>
          <span className="text-xs">Heatmap unavailable</span>
        </div>
      ) : imgSrc ? (
        <div className="relative">
          <img
            key={imgSrc}               /* force re-mount on URL change */
            src={imgSrc}
            alt="PPE violation density heatmap"
            className="w-full rounded-lg border border-slate-800/30 bg-black"
          />
          {frameCount === 0 && (
            <div className="absolute inset-0 flex flex-col items-center justify-center
                            bg-black/60 rounded-lg gap-1.5">
              <Flame size={20} className="text-slate-600"/>
              <span className="text-xs text-slate-500">Accumulating data…</span>
              <span className="text-[10px] text-slate-700">Violations will appear as heat</span>
            </div>
          )}
        </div>
      ) : (
        <div className="aspect-video bg-slate-900/40 border border-slate-800/30
                        rounded-lg flex items-center justify-center
                        text-slate-700 text-xs">
          Waiting for pipeline…
        </div>
      )}

      {/* Zone risk table */}
      {meta?.zone_risks?.length > 0 && (
        <div className="space-y-1.5">
          {meta.zone_risks.map(z => (
            <div key={z.zone_id}
                 className="flex items-center justify-between text-xs">
              <span className="text-slate-400 font-medium">{z.zone_id}</span>
              <div className="flex items-center gap-2">
                <span className="text-slate-600 tabular-nums">
                  {(z.violation_pct * 100).toFixed(0)}%
                </span>
                <span className={`px-2 py-0.5 rounded-md border text-xs font-medium
                  ${RISK_STYLES[z.risk_level] ?? 'text-slate-400 bg-slate-800 border-slate-700'}`}>
                  {z.risk_level}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default HeatmapPanel
