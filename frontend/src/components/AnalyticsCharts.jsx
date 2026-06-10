// src/components/AnalyticsCharts.jsx
import { useMemo } from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale,
  BarElement, ArcElement,
  LineElement, PointElement,
  Title, Tooltip, Legend,
} from 'chart.js'
import { Bar, Doughnut }    from 'react-chartjs-2'
import { AlertTriangle, TrendingUp }    from 'lucide-react'
import { useStats }         from '../hooks/useViolations'

ChartJS.register(
  CategoryScale, LinearScale,
  BarElement, ArcElement,
  LineElement, PointElement,
  Title, Tooltip, Legend,
)

const DARK = {
  surface : '#111520',
  border  : '#1e2a42',
  muted   : '#475569',
  label   : '#64748b',
  tooltip : '#0d1117',
}

const CHART_DEFAULTS = {
  plugins: {
    legend : { labels: { color: DARK.label, font: { size: 11 } } },
    tooltip: { backgroundColor: DARK.tooltip, borderColor: DARK.border, borderWidth: 1 },
  },
  scales: {
    x: { ticks: { color: DARK.muted }, grid: { color: 'rgba(30,42,66,0.6)' } },
    y: { ticks: { color: DARK.muted }, grid: { color: 'rgba(30,42,66,0.6)' } },
  },
}

const BAR_COLORS = [
  '#ef4444','#f97316','#3b82f6',
  '#10b981','#a855f7','#06b6d4',
  '#f59e0b','#6366f1',
]
const DONUT_COLORS = ['#ef4444','#f97316','#3b82f6','#10b981','#a855f7','#06b6d4','#f59e0b','#6366f1']

export function AnalyticsCharts() {
  const { data: stats, isLoading, isError } = useStats()

  const barData = useMemo(() => {
    const byClass = stats?.by_class || {}
    const labels  = Object.keys(byClass)
    return {
      labels,
      datasets: [{
        label          : 'Violations',
        data           : Object.values(byClass),
        backgroundColor: labels.map((_, i) => BAR_COLORS[i % BAR_COLORS.length] + 'cc'),
        borderColor    : labels.map((_, i) => BAR_COLORS[i % BAR_COLORS.length]),
        borderWidth    : 1,
        borderRadius   : 5,
        borderSkipped  : false,
      }],
    }
  }, [stats])

  const donutData = useMemo(() => {
    const byZone = stats?.by_zone || {}
    const labels = Object.keys(byZone)
    return {
      labels,
      datasets: [{
        data           : Object.values(byZone),
        backgroundColor: labels.map((_, i) => DONUT_COLORS[i % DONUT_COLORS.length] + 'cc'),
        borderColor    : labels.map((_, i) => DONUT_COLORS[i % DONUT_COLORS.length]),
        borderWidth    : 1,
      }],
    }
  }, [stats])

  if (isLoading) {
    return (
      <div className="bg-[#0d1117] border border-slate-800/60 rounded-xl
                      p-4 text-slate-600 text-sm flex items-center
                      justify-center h-48">
        Loading analytics…
      </div>
    )
  }

  if (isError) {
    return (
      <div className="bg-[#0d1117] border border-slate-800/60 rounded-xl
                      p-4 flex flex-col items-center justify-center
                      h-48 gap-2 text-red-400/70">
        <AlertTriangle size={18}/>
        <p className="text-sm">Failed to load analytics</p>
      </div>
    )
  }

  if (!stats) return null

  const SUMMARY = [
    { label: 'Total violations', value: stats.total_violations, color: 'text-red-400' },
    { label: 'Unacknowledged',   value: stats.unacknowledged,   color: 'text-orange-400' },
    { label: 'Zones monitored',  value: donutData.labels.length, color: 'text-blue-400' },
  ]

  return (
    <div className="flex flex-col gap-4">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-3">
        {SUMMARY.map(c => (
          <div key={c.label}
               className="bg-[#0d1117] border border-slate-800/60 rounded-xl
                          p-4 text-center">
            <p className={`text-3xl font-bold tabular-nums ${c.color}`}>{c.value}</p>
            <p className="text-slate-600 text-xs mt-1">{c.label}</p>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#0d1117] border border-slate-800/60 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={13} className="text-slate-500"/>
            <p className="text-xs font-medium text-slate-300">Violations by class</p>
          </div>
          <div className="h-64">
            <Bar
              data={barData}
              options={{
                ...CHART_DEFAULTS,
                responsive: true,
                maintainAspectRatio: false,
                plugins   : { ...CHART_DEFAULTS.plugins, legend: { display: false } },
              }}
            />
          </div>
        </div>

        <div className="bg-[#0d1117] border border-slate-800/60 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={13} className="text-slate-500"/>
            <p className="text-xs font-medium text-slate-300">Violations by zone</p>
          </div>
          {donutData.labels.length > 0 ? (
            <div className="h-64">
              <Doughnut
                data={donutData}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    ...CHART_DEFAULTS.plugins,
                    legend: {
                      position: 'right',
                      labels  : { color: DARK.label, font: { size: 11 }, padding: 16 },
                    },
                  },
                }}
              />
            </div>
          ) : (
            <p className="text-slate-700 text-sm text-center py-12">
              No zone data yet
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default AnalyticsCharts
