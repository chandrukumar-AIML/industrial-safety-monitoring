/**
 * useDemoMode — shared hook to detect whether the backend is in demo mode.
 *
 * Why: in demo mode there is no live camera/pipeline, so live KPIs (fps, active
 * tracks) are legitimately 0 and the WebSocket never connects. Several components
 * (StatusBar, StatCards, LiveFeed) need to know this so they can show friendly
 * demo states instead of looking "broken" (0/0/0.0 + red Offline + dead stream).
 *
 * Reuses the same react-query key as DemoBanner so the /demo/status call is
 * fetched once and shared across the tree.
 */
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

async function fetchDemoStatus() {
  // Use the shared axios client so the Authorization header is attached.
  // (A raw fetch has no auth → 401 in production → demo mode wrongly reads OFF.)
  try {
    const res = await api.get('/demo/status')
    return res.data
  } catch {
    return { demo_mode: false }
  }
}

export function useDemoMode() {
  const { data } = useQuery({
    queryKey: ['demo-status'],
    queryFn: fetchDemoStatus,
    staleTime: 60_000,
    retry: false,
  })
  return Boolean(data?.demo_mode)
}

export default useDemoMode
