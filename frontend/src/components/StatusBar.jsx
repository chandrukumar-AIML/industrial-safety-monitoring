// src/components/StatusBar.jsx
import PropTypes from 'prop-types'
import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../api/client'
import { Activity, Wifi, WifiOff, ShieldCheck } from 'lucide-react'
import { useDemoMode } from '../hooks/useDemoMode'

export function StatusBar({
  wsConnected = false,
  fps         = 0,
  violations  = 0,
}) {
  const isDemo = useDemoMode()
  const { data: health, isError: healthError } = useQuery({
    queryKey       : ['health'],
    queryFn        : () => getHealth().then(r => r.data),
    refetchInterval: 10_000,
  })

  return (
    <header
      className="bg-[#0d1117] border-b border-slate-800/60
                 px-5 py-2.5 flex items-center justify-between
                 sticky top-0 z-20"
      role="banner"
    >
      {/* Brand */}
      <div className="flex items-center gap-2.5">
        <div className="flex items-center justify-center w-7 h-7
                        rounded-lg bg-orange-500/15 border border-orange-500/30">
          <ShieldCheck size={14} className="text-orange-400"/>
        </div>
        <span className="font-semibold text-sm text-slate-100 tracking-tight">
          SafeGuard<span className="text-brand-500">AI</span>
        </span>
        <span className="text-xs text-slate-600 hidden sm:inline">
          Industrial Safety Monitoring
        </span>
      </div>

      {/* Status pills */}
      <div className="flex items-center gap-3 text-xs">

        {/* Live-pipeline status — only in live mode. In demo mode the top
            banner already communicates "demo", so we don't duplicate it here. */}
        {!isDemo && (
          <>
            <span
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full
                border font-medium ${
                  wsConnected
                    ? 'bg-green-500/10 border-green-500/30 text-green-400'
                    : 'bg-red-500/10  border-red-500/30  text-red-400'
                }`}
              aria-label={wsConnected ? 'Live stream connected' : 'Reconnecting'}
            >
              {wsConnected ? <Wifi size={11}/> : <WifiOff size={11}/>}
              {wsConnected ? 'Live' : 'Offline'}
            </span>

            <span className="flex items-center gap-1.5 text-slate-400"
                  aria-label={`${fps.toFixed(1)} frames per second`}>
              <Activity size={12} className="text-slate-500"/>
              <span className="font-mono">{Number(fps).toFixed(1)}</span>
              <span className="text-slate-600">fps</span>
            </span>
          </>
        )}

        {/* Live violations badge — live mode only (demo uses dashboard KPIs) */}
        {!isDemo && (violations > 0 ? (
          <span className="flex items-center gap-1 px-2.5 py-1 rounded-full
                           bg-red-500/15 border border-red-500/40 text-red-400
                           font-medium animate-pulse" aria-live="polite">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 inline-block"/>
            {violations} violation{violations !== 1 ? 's' : ''}
          </span>
        ) : (
          <span className="flex items-center gap-1 px-2.5 py-1 rounded-full
                           bg-green-500/10 border border-green-500/25 text-green-500
                           font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block"/>
            Clear
          </span>
        ))}

        {/* Model / device info */}
        {health && !healthError && (
          <span className="text-slate-600 hidden lg:flex items-center gap-1.5
                           pl-3 border-l border-slate-800">
            <span className="text-slate-500">
              {health.model_path?.split('/').pop() ?? 'unknown'}
            </span>
            <span className="text-slate-700">·</span>
            <span className="text-slate-500 uppercase text-[10px] tracking-wider">
              {health.device ?? 'cpu'}
            </span>
          </span>
        )}
        {healthError && (
          <span className="text-slate-700 hidden lg:block pl-3 border-l border-slate-800">
            API unreachable
          </span>
        )}
      </div>
    </header>
  )
}

StatusBar.propTypes = {
  wsConnected: PropTypes.bool,
  fps        : PropTypes.number,
  violations : PropTypes.number,
}

export default StatusBar
