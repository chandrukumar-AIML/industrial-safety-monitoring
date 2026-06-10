/**
 * frontend/src/hooks/useWebSocket.js
 *
 * Manages WebSocket connection for live video stream with auto-reconnect.
 *
 * # FIXED: Proper cleanup on unmount (prevent memory leaks)
 * # FIXED: Exponential backoff for reconnection attempts
 * # IMPROVED: JSDoc types for IDE autocomplete
 * # FIXED: Error handling without crashing the component
 * # IMPROVED: Connection state management (connecting/connected/disconnected)
 * # FIXED: Message validation to prevent XSS via malformed JSON
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { createStreamSocket } from '../api/client'

// Reconnection config
const MAX_RETRIES = 10
const INITIAL_RETRY_DELAY_MS = 1_000
const MAX_RETRY_DELAY_MS = 30_000
const RETRY_BACKOFF_MULTIPLIER = 1.5

/**
 * @typedef {Object} StreamFrame
 * @property {'frame'} type
 * @property {string} timestamp
 * @property {number} frame_idx
 * @property {string} jpeg_b64
 * @property {number} active_tracks
 * @property {number} active_violations
 * @property {number} fps
 */

/**
 * @typedef {Object} UseWebSocketReturn
 * @property {StreamFrame|null} frame - Latest frame data
 * @property {boolean} connected - True if WebSocket is open
 * @property {boolean} connecting - True while attempting to connect
 * @property {number} fps - Current pipeline FPS (from latest frame)
 * @property {number} violations - Active violations count (from latest frame)
 * @property {number} retryCount - Current reconnection attempt count
 * @property {() => void} reconnect - Manual reconnect trigger
 * @property {() => void} disconnect - Manual disconnect
 */

/**
 * Manages a WebSocket connection to the frame stream endpoint.
 * 
 * @param {Object} [options]
 * @param {number} [options.pingMs=20000] - Keepalive ping interval in ms
 * @param {boolean} [options.autoReconnect=true] - Auto-reconnect on disconnect
 * @returns {UseWebSocketReturn}
 * 
 * @example
 * const { frame, connected, fps, violations } = useWebSocket()
 * if (!connected) return <ConnectionStatus />
 * return <VideoFrame src={`data:image/jpeg;base64,${frame.jpeg_b64}`} />
 */
export function useWebSocket(options = {}) {
  const {
    pingMs = 20_000,
    autoReconnect = true,
  } = options

  // Validate config
  const validatedPingMs = Math.min(60_000, Math.max(5_000, pingMs))
  if (validatedPingMs !== pingMs) {
    console.warn(`useWebSocket: pingMs clamped to ${validatedPingMs}ms`)
  }

  const [state, setState] = useState({
    frame: null,
    connected: false,
    connecting: true,
    fps: 0,
    violations: 0,
  })

  // Refs for cleanup and avoiding stale closures
  const socketRef = useRef(null)
  const retryCountRef = useRef(0)
  const retryTimeoutRef = useRef(null)
  const isMountedRef = useRef(true)
  const lastFrameTimeRef = useRef(0)

  // Calculate next retry delay with exponential backoff + jitter
  const calculateRetryDelay = useCallback((attempt) => {
    const delay = Math.min(
      MAX_RETRY_DELAY_MS,
      INITIAL_RETRY_DELAY_MS * (RETRY_BACKOFF_MULTIPLIER ** attempt)
    )
    // Add jitter (±20%) to prevent thundering herd
    const jitter = delay * 0.2 * (Math.random() - 0.5)
    return Math.round(delay + jitter)
  }, [])

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (socketRef.current || !isMountedRef.current) return

    setState(prev => ({ ...prev, connecting: true }))

    try {
      socketRef.current = createStreamSocket(
        // onMessage
        (msg) => {
          if (!isMountedRef.current) return
          
          // Validate message type
          if (msg?.type === 'pong') {
            // Keepalive response — no action needed
            return
          }
          
          if (msg?.type === 'frame' && typeof msg.jpeg_b64 === 'string') {
            // Basic validation: ensure required fields exist
            if (
              typeof msg.frame_idx !== 'number' ||
              typeof msg.fps !== 'number' ||
              typeof msg.active_violations !== 'number'
            ) {
              console.warn('[WS] Invalid frame message structure:', msg)
              return
            }
            
            // Update state with new frame
            setState({
              frame: msg,
              connected: true,
              connecting: false,
              fps: msg.fps,
              violations: msg.active_violations,
            })
            
            // Track last frame time for FPS calculation
            lastFrameTimeRef.current = Date.now()
            
            // Reset retry count on successful message
            retryCountRef.current = 0
          }
        },
        // onClose — called for normal close, error, or manual close
        () => {
          if (!isMountedRef.current) return
          
          socketRef.current = null
          
          setState(prev => ({
            ...prev,
            connected: false,
            connecting: false,
          }))
          
          // Auto-reconnect if enabled and under retry limit
          if (autoReconnect && retryCountRef.current < MAX_RETRIES) {
            const delay = calculateRetryDelay(retryCountRef.current)
            retryCountRef.current += 1
            
            if (import.meta.env.DEV) {
              console.debug(`[WS] Reconnecting in ${delay}ms (attempt ${retryCountRef.current}/${MAX_RETRIES})`)
            }
            
            retryTimeoutRef.current = setTimeout(() => {
              if (isMountedRef.current) {
                connect()
              }
            }, delay)
          } else if (retryCountRef.current >= MAX_RETRIES) {
            console.error('[WS] Max reconnection attempts reached')
          }
        },
        // onOpen — connection established
        () => {
          if (!isMountedRef.current) return
          
          setState(prev => ({ 
            ...prev, 
            connected: true, 
            connecting: false 
          }))
          
          if (import.meta.env.DEV) {
            console.debug('[WS] Connection established')
          }
        },
        validatedPingMs
      )
    } catch (err) {
      console.error('[WS] Failed to create socket:', err)
      setState(prev => ({
        ...prev,
        connected: false,
        connecting: false,
      }))
    }
  }, [autoReconnect, calculateRetryDelay, validatedPingMs])

  // Manual reconnect trigger
  const reconnect = useCallback(() => {
    retryCountRef.current = 0
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    connect()
  }, [connect])

  // Manual disconnect
  const disconnect = useCallback(() => {
    // Clear any pending reconnect
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    retryCountRef.current = MAX_RETRIES // Prevent auto-reconnect
    
    // Close socket
    socketRef.current?.close()
    socketRef.current = null
    
    setState(prev => ({
      ...prev,
      connected: false,
      connecting: false,
    }))
  }, [])

  // Effect: Connect on mount, cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    
    // Initial connection
    connect()
    
    // Cleanup function
    return () => {
      isMountedRef.current = false
      
      // Clear reconnect timeout
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current)
        retryTimeoutRef.current = null
      }
      
      // Close WebSocket
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [connect])

  return {
    frame: state.frame,
    connected: state.connected,
    connecting: state.connecting,
    fps: state.fps,
    violations: state.violations,
    retryCount: retryCountRef.current,
    reconnect,
    disconnect,
  }
}