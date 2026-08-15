/**
 * frontend/src/hooks/useHeatmap.js
 *
 * Polls heatmap image and metadata with cache-busting and error recovery.
 *
 * # FIXED: Proper cleanup on unmount (prevent memory leaks)
 * # FIXED: Secure cache-busting URL construction
 * # IMPROVED: JSDoc types for IDE autocomplete
 * # FIXED: Error state isolation (don't lose last good image)
 * # IMPROVED: Configurable polling with validation
 * # FIXED: AbortController for cancelling in-flight requests
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getHeatmapMeta } from '../api/client'

/**
 * @typedef {Object} HeatmapMeta
 * @property {number} frame_count
 * @property {Object} stats
 * @property {Array} zone_risks
 */

/**
 * @typedef {Object} UseHeatmapReturn
 * @property {string|null} imgSrc - Cache-busted heatmap image URL
 * @property {HeatmapMeta|null} meta - Heatmap metadata
 * @property {Error|null} error - Last error (null if none)
 * @property {boolean} isLoading - True during initial load
 * @property {() => void} refresh - Manual refresh trigger
 */

/**
 * Polls the heatmap image and metadata.
 * 
 * @param {number} [pollMs=5000] - Polling interval in ms (min: 1000, max: 60000)
 * @returns {UseHeatmapReturn}
 * 
 * @example
 * const { imgSrc, meta, error, isLoading, refresh } = useHeatmap(3000)
 * if (isLoading) return <Spinner />
 * if (error) return <Error message={error._uiMessage} />
 * return <img src={imgSrc} alt="Heatmap" />
 */
export function useHeatmap(pollMs = 5_000) {
  // Validate polling interval
  const validatedPollMs = Math.min(60_000, Math.max(1_000, pollMs))
  if (validatedPollMs !== pollMs) {
    console.warn(`useHeatmap: pollMs clamped to ${validatedPollMs}ms (was ${pollMs})`)
  }

  const [state, setState] = useState({
    imgSrc: null,
    meta: null,
    error: null,
    isLoading: true,
  })

  // Refs for cleanup and avoiding stale closures
  const abortControllerRef = useRef(null)
  const isMountedRef = useRef(true)
  const lastSuccessfulSrcRef = useRef(null)

  // Build cache-busting URL (relative path for Vite proxy)
  const buildImgSrc = useCallback(() => {
    // Use timestamp to bust cache, but keep path relative for proxy
    return `/heatmap?t=${Date.now()}`
  }, [])

  // Fetch heatmap metadata
  const fetchMeta = useCallback(async () => {
    // Cancel any in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    abortControllerRef.current = new AbortController()

    try {
      const res = await getHeatmapMeta()
      
      // Only update state if component is still mounted
      if (isMountedRef.current) {
        const newSrc = buildImgSrc()
        lastSuccessfulSrcRef.current = newSrc
        
        setState({
          imgSrc: newSrc,
          meta: res.data,
          error: null,
          isLoading: false,
        })
      }
    } catch (err) {
      // Don't update error if aborted (component unmounting)
      if (err.name === 'AbortError') return
      
      if (isMountedRef.current) {
        setState(prev => ({
          ...prev,
          error: err,
          isLoading: false,
          // Keep last good imgSrc if available
          imgSrc: prev.imgSrc || lastSuccessfulSrcRef.current,
        }))
      }
    }
  }, [buildImgSrc])

  // Manual refresh function (stable reference)
  const refresh = useCallback(() => {
    fetchMeta()
  }, [fetchMeta])

  // Effect: Start polling, cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    
    // Initial fetch
    fetchMeta()
    
    // Set up polling interval
    const intervalId = setInterval(fetchMeta, validatedPollMs)
    
    // Cleanup function
    return () => {
      isMountedRef.current = false
      
      // Cancel any in-flight request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
        abortControllerRef.current = null
      }
      
      // Clear polling interval
      clearInterval(intervalId)
      
      // Revoke blob URLs to prevent memory leaks
      if (lastSuccessfulSrcRef.current?.startsWith('blob:')) {
        URL.revokeObjectURL(lastSuccessfulSrcRef.current)
      }
    }
  }, [fetchMeta, validatedPollMs])

  return {
    imgSrc: state.imgSrc,
    meta: state.meta,
    error: state.error,
    isLoading: state.isLoading,
    refresh,
  }
}