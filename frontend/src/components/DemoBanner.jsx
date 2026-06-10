/**
 * frontend/src/components/DemoBanner.jsx
 *
 * Banner shown when DEMO_MODE is active.
 * Fetches /demo/status to check if demo mode is enabled on the server.
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

async function fetchDemoStatus() {
  // Use the authenticated client (raw fetch has no auth → 401 in production).
  try {
    const res = await api.get('/demo/status')
    return res.data
  } catch {
    return { demo_mode: false }
  }
}

export default function DemoBanner() {
  const { data } = useQuery({
    queryKey: ['demo-status'],
    queryFn: fetchDemoStatus,
    staleTime: 60_000,
    retry: false,
  })

  if (!data?.demo_mode) return null

  return (
    <div className="bg-amber-500/20 border-b border-amber-500/40 px-4 py-2 flex items-center gap-2.5 text-sm">
      <span className="text-amber-400 text-lg">🎭</span>
      <span className="text-amber-300 font-semibold">You're exploring the SafeGuardAI demo</span>
      <span className="text-amber-400/80 hidden sm:inline">
        — sample data across 8 industries. Every feature is fully interactive.
      </span>
    </div>
  )
}
