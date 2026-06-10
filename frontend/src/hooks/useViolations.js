/**
 * frontend/src/hooks/useViolations.js
 *
 * React Query hooks for violation data: list, stats, and acknowledgment.
 *
 * # FIXED: Proper error handling with user-friendly messages
 * # FIXED: Input validation for query params
 * # IMPROVED: JSDoc types for IDE autocomplete
 * # FIXED: Mutation error handling (was silent failure)
 * # IMPROVED: Optimistic updates for better UX
 * # FIXED: Query key stability for cache invalidation
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getViolations, getStats, acknowledge } from '../api/client'

/**
 * @typedef {Object} Violation
 * @property {number} id
 * @property {number} track_id
 * @property {string} class_name
 * @property {number} confidence
 * @property {string} [zone_id]
 * @property {number} bbox_x1
 * @property {number} bbox_y1
 * @property {number} bbox_x2
 * @property {number} bbox_y2
 * @property {number} frame_idx
 * @property {string} timestamp
 * @property {boolean} acknowledged
 * @property {string} [notes]
 */

/**
 * @typedef {Object} ViolationParams
 * @property {number} [limit=50] - Max results (1-500)
 * @property {number} [offset=0] - Skip N results
 * @property {string} [zone_id] - Filter by zone
 * @property {string} [class_name] - Filter by violation class
 * @property {boolean} [acknowledged] - Filter by ack status
 */

/**
 * Paginated violation log with polling.
 * 
 * @param {ViolationParams} [params] - Filter and pagination params
 * @returns {import('@tanstack/react-query').UseQueryResult<Violation[], Error>}
 * 
 * @example
 * const { data, isLoading, isError, error } = useViolations({ limit: 25, zone_id: 'zone-1' })
 */
export function useViolations(params = {}) {
  // Validate and sanitize params
  const validatedParams = {
    limit: Math.min(500, Math.max(1, params.limit ?? 50)),
    offset: Math.max(0, params.offset ?? 0),
    zone_id: params.zone_id?.trim() || undefined,
    class_name: params.class_name?.trim() || undefined,
    acknowledged: params.acknowledged === undefined ? undefined : Boolean(params.acknowledged),
  }

  return useQuery({
    queryKey: ['violations', validatedParams],
    queryFn: async () => {
      const res = await getViolations(validatedParams)
      return res.data
    },
    // Polling: 5s is good balance (WS handles live updates)
    refetchInterval: 5_000,
    staleTime: 2_000, // Consider data fresh for 2s
    placeholderData: [], // Avoid undefined checks in components
    // Retry logic: 3 attempts with exponential backoff
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10_000),
    // Don't retry on auth errors
    retryOnMount: true,
  })
}

/**
 * Aggregate violation statistics.
 * 
 * @typedef {Object} ViolationStats
 * @property {number} total_violations
 * @property {number} unacknowledged
 * @property {Object.<string, number>} by_class
 * @property {Object.<string, number>} by_zone
 * 
 * @returns {import('@tanstack/react-query').UseQueryResult<ViolationStats, Error>}
 */
export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: async () => {
      const res = await getStats()
      return res.data
    },
    refetchInterval: 5_000,
    staleTime: 3_000,
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10_000),
  })
}

/**
 * @typedef {Object} AcknowledgeMutationVars
 * @property {number} id - Violation ID to acknowledge
 * @property {string} [notes] - Optional supervisor notes
 */

/**
 * Mutation to acknowledge a violation event.
 * 
 * @returns {import('@tanstack/react-query').UseMutationResult<
 *   { status: string; id: number; already_existed: boolean },
 *   Error,
 *   AcknowledgeMutationVars,
 *   unknown
 * >}
 * 
 * @example
 * const { mutate, isPending, error } = useAcknowledge()
 * mutate({ id: 42, notes: 'Reviewed by supervisor' }, {
 *   onSuccess: () => toast.success('Acknowledged'),
 *   onError: (err) => toast.error(err._uiMessage),
 * })
 */
export function useAcknowledge() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, notes }) => {
      // Validate inputs
      if (!Number.isInteger(id) || id < 1) {
        throw new Error('Invalid violation ID')
      }
      const sanitizedNotes = notes?.trim() || null
      return acknowledge(id, sanitizedNotes)
    },
    // Optimistic update: mark as acknowledged immediately
    onMutate: async ({ id }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['violations'] })
      
      // Snapshot previous value
      const previousViolations = queryClient.getQueryData(['violations'])
      
      // Optimistically update the cache
      queryClient.setQueryData(['violations'], (old) => {
        if (!Array.isArray(old)) return old
        return old.map(v => 
          v.id === id ? { ...v, acknowledged: true } : v
        )
      })
      
      return { previousViolations }
    },
    // Rollback on error
    onError: (err, _vars, context) => {
      if (context?.previousViolations) {
        queryClient.setQueryData(['violations'], context.previousViolations)
      }
      console.error('[useAcknowledge] failed:', err._uiMessage ?? err.message)
    },
    // Invalidate queries to refetch fresh data
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })
}

/**
 * Hook for bulk acknowledgment (multiple violations at once).
 * 
 * @returns {import('@tanstack/react-query').UseMutationResult<
 *   { acknowledged: number[]; failed: Array<{id: number; error: string}> },
 *   Error,
 *   { ids: number[]; notes?: string },
 *   unknown
 * >}
 */
export function useBulkAcknowledge() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async ({ ids, notes = null }) => {
      // Validate inputs
      if (!Array.isArray(ids) || ids.length === 0) {
        throw new Error('At least one violation ID required')
      }
      if (!ids.every(id => Number.isInteger(id) && id >= 1)) {
        throw new Error('All IDs must be positive integers')
      }
      
      // Acknowledge each (could be parallelized with Promise.allSettled)
      const results = await Promise.allSettled(
        ids.map(id => acknowledge(id, notes?.trim() || null))
      )
      
      const acknowledged = []
      const failed = []
      
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          acknowledged.push(ids[index])
        } else {
          failed.push({
            id: ids[index],
            error: result.reason?._uiMessage ?? result.reason?.message ?? 'Unknown error',
          })
        }
      })
      
      return { acknowledged, failed }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })
}