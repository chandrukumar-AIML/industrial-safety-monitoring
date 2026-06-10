// src/components/StatCards.jsx
import { useMemo } from 'react'
import PropTypes from 'prop-types'
import { ShieldAlert, Users, Zap, BarChart2, AlertOctagon, MapPin, CheckCircle2 } from 'lucide-react'
import { useStats } from '../hooks/useViolations'
import { useDemoMode } from '../hooks/useDemoMode'

export function StatCards({
  fps          = 0,
  violations   = 0,
  activeTracks = 0,
}) {
  const { data: stats } = useStats()
  const isDemo = useDemoMode()

  const cards = useMemo(() => {
    // ── Demo mode: live pipeline KPIs are legitimately 0, so surface the rich
    //    aggregate data instead of 0 / 0 / 0.0 (which reads as "broken"). ──
    if (isDemo) {
      const total = stats?.total_violations ?? 0
      const unack = stats?.unacknowledged ?? 0
      const zones = stats?.by_zone ? Object.keys(stats.by_zone).length : 0
      const compliance = total > 0
        ? Math.max(0, Math.round((1 - unack / Math.max(total, 1)) * 100))
        : 100
      return [
        {
          icon: <BarChart2 size={20}/>, label: 'Total Violations', value: total,
          accent: { ring: 'border-red-500/40', bg: 'bg-red-500/8', icon: 'text-red-400', val: 'text-red-300' },
        },
        {
          icon: <AlertOctagon size={20}/>, label: 'Unacknowledged', value: unack,
          accent: { ring: 'border-orange-500/30', bg: 'bg-orange-500/6', icon: 'text-orange-400', val: 'text-orange-300' },
        },
        {
          icon: <MapPin size={20}/>, label: 'Zones Monitored', value: zones,
          accent: { ring: 'border-blue-500/30', bg: 'bg-blue-500/6', icon: 'text-blue-400', val: 'text-blue-300' },
        },
        {
          icon: <CheckCircle2 size={20}/>, label: 'Compliance', value: `${compliance}%`,
          accent: { ring: 'border-emerald-500/30', bg: 'bg-emerald-500/6', icon: 'text-emerald-400', val: 'text-emerald-300' },
        },
      ]
    }

    // ── Live mode: real-time pipeline KPIs ──
    return [
      {
        icon : <ShieldAlert size={20}/>,
        label: 'Active Violations',
        value: violations,
        accent: violations > 0
          ? { ring: 'border-red-500/40', bg: 'bg-red-500/8', icon: 'text-red-400', val: 'text-red-300' }
          : { ring: 'border-green-500/30', bg: 'bg-green-500/6', icon: 'text-green-400', val: 'text-green-300' },
      },
      {
        icon : <Users size={20}/>,
        label: 'Active Tracks',
        value: activeTracks,
        accent: { ring: 'border-blue-500/30', bg: 'bg-blue-500/6', icon: 'text-blue-400', val: 'text-blue-300' },
      },
      {
        icon : <Zap size={20}/>,
        label: 'Pipeline FPS',
        value: Number(fps).toFixed(1),
        accent: fps >= 20
          ? { ring: 'border-emerald-500/30', bg: 'bg-emerald-500/6', icon: 'text-emerald-400', val: 'text-emerald-300' }
          : { ring: 'border-yellow-500/30',  bg: 'bg-yellow-500/6',  icon: 'text-yellow-400', val: 'text-yellow-300' },
      },
      {
        icon : <BarChart2 size={20}/>,
        label: 'Total Today',
        value: stats?.total_violations ?? '—',
        accent: { ring: 'border-orange-500/30', bg: 'bg-orange-500/6', icon: 'text-orange-400', val: 'text-orange-300' },
      },
    ]
  }, [isDemo, fps, violations, activeTracks, stats?.total_violations, stats?.unacknowledged, stats?.by_zone])

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map(c => (
        <div
          key={c.label}
          className={`${c.accent.bg} ${c.accent.ring}
            border rounded-xl p-4 flex items-center gap-3
            transition-all duration-200`}
          role="status"
          aria-label={`${c.label}: ${c.value}`}
        >
          <div className={`${c.accent.icon} shrink-0`}>{c.icon}</div>
          <div className="min-w-0">
            <p className={`text-2xl font-bold tabular-nums leading-none mb-1 ${c.accent.val}`}>
              {c.value}
            </p>
            <p className="text-slate-500 text-xs truncate">{c.label}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

StatCards.propTypes = {
  fps         : PropTypes.number,
  violations  : PropTypes.number,
  activeTracks: PropTypes.number,
}

export default StatCards
