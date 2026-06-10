/**
 * frontend/src/api/client.js
 *
 * Axios HTTP client + WebSocket factory for Industrial Safety Monitor.
 *
 * # FIXED: Authentication header injection for all requests
 * # FIXED: Secure WebSocket URL construction (wss:// in production)
 * # FIXED: Proper error handling with user-friendly messages
 * # IMPROVED: JSDoc types for IDE autocomplete and type safety
 * # FIXED: Memory leak prevention (ping interval cleanup)
 * # IMPROVED: Environment variable validation at module load
 * # FIXED: XSS protection in error messages
 */

import axios from 'axios'

// ── Environment validation ───────────────────────────────────
const validateEnv = () => {
  const required = ['VITE_API_URL']
  const missing = required.filter(key => !import.meta.env[key])
  
  if (missing.length > 0 && import.meta.env.PROD) {
    console.error('❌ Missing required environment variables:', missing.join(', '))
    // In production, fail fast to avoid silent misconfiguration
    throw new Error(`Missing env vars: ${missing.join(', ')}`)
  }
  
  // Warn in development
  if (missing.length > 0) {
    console.warn('⚠️  Missing environment variables (dev mode):', missing.join(', '))
  }
}

// Run validation immediately
validateEnv()

// ── Configuration ─────────────────────────────────────────────
const BASE_URL = import.meta.env.VITE_API_URL || ''
const WS_BASE_URL = import.meta.env.VITE_WS_URL || null
const API_KEY = import.meta.env.VITE_API_KEY || ''
const REQUEST_TIMEOUT = parseInt(import.meta.env.VITE_REQUEST_TIMEOUT || '10000', 10)
const WS_PING_INTERVAL = parseInt(import.meta.env.VITE_WS_PING_INTERVAL || '20000', 10)

// Security: Only allow HTTPS/WSS in production
const isProduction = import.meta.env.PROD
const requireSecure = isProduction && !import.meta.env.VITE_ALLOW_INSECURE

if (requireSecure && BASE_URL.startsWith('http://')) {
  console.warn('⚠️  Production mode: Consider using HTTPS for API_BASE_URL')
}

// ── HTTP Client Setup ─────────────────────────────────────────
/**
 * @typedef {Object} ApiError
 * @property {number} [status] - HTTP status code
 * @property {string} message - Error message
 * @property {Object} [data] - Response data
 * @property {boolean} isNetworkError - True if network failure
 */

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: REQUEST_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
    // Security: Prevent MIME type sniffing
    'X-Content-Type-Options': 'nosniff',
  },
})

// Request interceptor: Attach auth header if API key exists
api.interceptors.request.use(
  (config) => {
    if (API_KEY && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${API_KEY}`
    }
    // Security: Prevent caching of sensitive endpoints
    if (config.url?.includes('/agent/') || config.url?.includes('/reports/')) {
      config.headers['Cache-Control'] = 'no-store'
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: Unified error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Determine error type
    const isNetworkError = !error.response
    const status = error.response?.status
    const serverMessage = error.response?.data?.detail || error.response?.data?.message
    
    // Sanitize error message to prevent XSS in UI
    const sanitize = (str) => {
      if (typeof str !== 'string') return 'Unknown error'
      // Escape HTML special characters
      return str.replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[char])
    }
    
    // Build user-friendly message
    let uiMessage = 'An unexpected error occurred'
    
    if (isNetworkError) {
      uiMessage = 'Network error — please check your connection'
    } else if (status === 401) {
      uiMessage = 'Authentication required — please log in again'
    } else if (status === 403) {
      uiMessage = 'Access denied — insufficient permissions'
    } else if (status === 404) {
      uiMessage = 'Resource not found'
    } else if (status === 429) {
      uiMessage = 'Too many requests — please wait before trying again'
    } else if (status >= 500) {
      uiMessage = 'Server error — please try again later'
    } else if (serverMessage) {
      uiMessage = sanitize(serverMessage)
    }
    
    // Log detailed error for debugging (without PII)
    if (import.meta.env.DEV) {
      console.error('API Error:', {
        url: error.config?.url,
        method: error.config?.method,
        status,
        message: serverMessage,
        isNetworkError,
      })
    }
    
    // Return enriched error for React Query / UI components
    return Promise.reject(
      Object.assign(error, {
        _uiMessage: uiMessage,
        _isNetworkError: isNetworkError,
        _status: status,
      })
    )
  }
)

// ── REST API Endpoints ────────────────────────────────────────
/**
 * @typedef {Object} HealthResponse
 * @property {string} status - 'ok' or 'degraded'
 * @property {boolean} pipeline_running
 * @property {number} active_tracks
 * @property {number} fps
 */

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
 * @typedef {Object} Detection
 * @property {number} track_id
 * @property {string} class_name
 * @property {number} confidence
 * @property {[number, number, number, number]} bbox_xyxy
 * @property {string} [zone_id]
 * @property {boolean} is_violation
 * @property {number} frame_idx
 */

// System endpoints
export const getHealth = () => api.get('/health')

// Detection endpoints
export const getViolations = (params = {}) => 
  api.get('/detections', { 
    params: { 
      limit: 50, 
      offset: 0, 
      ...params 
    } 
  })

export const getStats = () => api.get('/detections/stats')
export const getLive = () => api.get('/detections/live')

// Heatmap endpoints
export const getHeatmapMeta = () => api.get('/heatmap/meta')
export const resetHeatmap = () => api.post('/heatmap/reset')

// SHAP endpoint - FIXED: POST with /explain suffix
export const getSHAP = (trackId) => {
  if (!Number.isInteger(trackId) || trackId < 0) {
    return Promise.reject(new Error('Invalid trackId'))
  }
  return api.post(`/shap/${trackId}/explain`)
}

// Acknowledgment endpoint
export const acknowledge = (id, notes = null) => {
  if (!Number.isInteger(id) || id < 1) {
    return Promise.reject(new Error('Invalid violation ID'))
  }
  return api.patch(`/detections/${id}/acknowledge`, { 
    notes: notes?.trim() || null 
  })
}

// ── WebSocket Factory ─────────────────────────────────────────
/**
 * @typedef {Object} StreamMessage
 * @property {'frame'|'pong'} type
 * @property {string} timestamp
 * @property {number} frame_idx
 * @property {string} jpeg_b64
 * @property {number} active_tracks
 * @property {number} active_violations
 * @property {number} fps
 */

/**
 * @typedef {Object} StreamSocket
 * @property {() => void} close - Close the WebSocket connection
 * @property {(msg: Object) => void} send - Send a message to the server
 * @property {boolean} isConnected - Current connection state
 */

/**
 * Creates a managed WebSocket connection for video streaming.
 * 
 * @param {(msg: StreamMessage) => void} onMessage - Called with parsed JSON payload
 * @param {() => void} onClose - Called on close OR error (single callback)
 * @param {() => void} [onOpen] - Called when socket handshake completes
 * @param {number} [pingMs] - Keepalive interval in milliseconds (default: 20000)
 * @returns {StreamSocket} Managed socket interface
 * 
 * @example
 * const socket = createStreamSocket(
 *   (msg) => setFrame(msg.jpeg_b64),
 *   () => setConnected(false),
 *   () => setConnected(true),
 *   15000
 * )
 * // Later: socket.close()
 */
export function createStreamSocket(
  onMessage,
  onClose,
  onOpen = null,
  pingMs = WS_PING_INTERVAL,
) {
  // Validate callbacks
  if (typeof onMessage !== 'function') {
    throw new TypeError('onMessage must be a function')
  }
  if (typeof onClose !== 'function') {
    throw new TypeError('onClose must be a function')
  }
  
  // Construct secure WebSocket URL
  let wsUrl
  if (WS_BASE_URL) {
    wsUrl = WS_BASE_URL
  } else {
    // Derive from current location with security check
    const protocol = window.location.protocol === 'https:' || requireSecure ? 'wss:' : 'ws:'
    wsUrl = `${protocol}//${window.location.host}`
  }
  
  // Append stream endpoint
  const fullUrl = `${wsUrl}/stream`
  
  if (import.meta.env.DEV) {
    console.debug('[WS] Connecting to:', fullUrl)
  }
  
  // Create WebSocket with protocols if needed
  const ws = new WebSocket(fullUrl)
  
  // Track connection state
  let isConnected = false
  let pingInterval = null
  let isClosing = false
  
  // Connection handlers
  ws.onopen = () => {
    isConnected = true
    isClosing = false
    
    if (import.meta.env.DEV) {
      console.debug('[WS] Connected successfully')
    }
    
    // Notify consumer
    onOpen?.()
    
    // Start keepalive ping
    pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, pingMs)
  }
  
  ws.onmessage = (event) => {
    if (!isConnected) return

    // FIXED: Guard against binary blobs (ArrayBuffer/Blob) before JSON.parse
    // A misconfigured server could send raw JPEG bytes — JSON.parse on binary throws
    // and was silently swallowed with no user feedback.
    if (typeof event.data !== 'string') {
      console.warn('[WS] Received unexpected binary message — expected JSON text. Ignoring.')
      return
    }

    try {
      // Parse JSON safely
      const msg = JSON.parse(event.data)

      // Validate message structure (basic)
      if (msg && typeof msg === 'object' && 'type' in msg) {
        onMessage(msg)
      } else {
        console.warn('[WS] Received invalid message structure:', msg)
      }
    } catch (err) {
      console.warn('[WS] Failed to parse message:', err.message)
      // Don't crash the socket on bad data
    }
  }
  
  // Unified close handler (called for normal close, error, or manual close)
  const handleClose = () => {
    if (isClosing) return
    isClosing = true
    isConnected = false
    
    // Clean up ping interval
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }
    
    if (import.meta.env.DEV) {
      console.debug('[WS] Connection closed')
    }
    
    // Notify consumer (single callback)
    onClose()
  }
  
  ws.onclose = handleClose
  
  ws.onerror = (error) => {
    if (import.meta.env.DEV) {
      console.error('[WS] Error event:', error)
    }
    
    // Note: onerror is always followed by onclose in browsers,
    // so handleClose() will be called automatically.
    // We don't call onClose() here to avoid duplicate notifications.
  }
  
  // Return managed interface
  return {
    get isConnected() {
      return isConnected && ws.readyState === WebSocket.OPEN
    },
    
    close: () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        isClosing = true
        ws.close(1000, 'Client initiated close')
      }
      // handleClose() will be called via onclose
    },
    
    send: (msg) => {
      // Only send if socket is open and not closing
      if (isConnected && ws.readyState === WebSocket.OPEN && !isClosing) {
        try {
          ws.send(JSON.stringify(msg))
          return true
        } catch (err) {
          console.error('[WS] Send failed:', err)
          return false
        }
      }
      return false
    },
  }
}

// ── Utility Functions ─────────────────────────────────────────
/**
 * Converts base64 JPEG to blob URL for efficient image rendering.
 * 
 * @param {string} base64 - Base64-encoded JPEG string
 * @returns {string} Blob URL (call URL.revokeObjectURL() when done)
 */
// FIXED: Callers MUST call URL.revokeObjectURL(url) when done to prevent memory leaks.
// For live video frames, revoke the previous URL before creating a new one.
export const base64ToBlobUrl = (base64) => {
  try {
    // Remove data URL prefix if present
    const cleanBase64 = base64.replace(/^data:image\/jpeg;base64,/, '')
    
    // Convert to binary string
    const binary = atob(cleanBase64)
    
    // Create byte array
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
    
    // Create blob and URL
    const blob = new Blob([bytes], { type: 'image/jpeg' })
    return URL.createObjectURL(blob)
  } catch (err) {
    console.error('Failed to convert base64 to blob:', err)
    return null
  }
}

/**
 * Formats timestamp for display in UI.
 * 
 * @param {string} isoString - ISO 8601 timestamp string
 * @param {boolean} showSeconds - Include seconds in output
 * @returns {string} Formatted time string
 */
export const formatTimestamp = (isoString, showSeconds = false) => {
  try {
    const date = new Date(isoString)
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: showSeconds ? '2-digit' : undefined,
      hour12: false,
    })
  } catch {
    return isoString // Fallback to original string
  }
}

/**
 * Gets human-readable violation class name.
 * 
 * @param {string} className - Machine-readable class name
 * @returns {string} Human-readable label
 */
export const formatViolationClass = (className) => {
  const labels = {
    'no helmet': 'Missing Hard Hat',
    'no vest': 'Missing Safety Vest',
    'no gloves': 'Missing Gloves',
    'no goggles': 'Missing Eye Protection',
    'no boots': 'Missing Safety Boots',
    'no mask': 'Missing Respirator',
    'no suit': 'Missing Protective Suit',
  }
  return labels[className] || className.replace(/no\s+/i, 'Missing ')
}

// Export config for debugging/testing
export const config = {
  baseUrl: BASE_URL,
  wsUrl: WS_BASE_URL,
  apiKeySet: !!API_KEY,
  isProduction,
  requireSecure,
}
// Alias for enterprise panel components
export const apiClient = api
