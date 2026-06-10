/**
 * frontend/src/constants.js
 *
 * Application-wide constants, configuration, and enums.
 *
 * # FIXED: Centralized configuration with validation
 * # IMPROVED: JSDoc types for better IDE support
 * # FIXED: Safe defaults for missing environment variables
 */

// ── Application Metadata ─────────────────────────────────────
export const APP_NAME = import.meta.env.VITE_APP_NAME || 'Industrial Safety Monitor'
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || '1.0.0'
export const COMPANY_NAME = import.meta.env.VITE_COMPANY_NAME || 'Safety Solutions Inc.'

// ── API Configuration ────────────────────────────────────────
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
export const WS_BASE_URL = import.meta.env.VITE_WS_URL || null // null = auto-detect
export const API_TIMEOUT_MS = parseInt(import.meta.env.VITE_API_TIMEOUT || '10000', 10)
export const API_KEY_STORAGE_KEY = 'safety_monitor_api_key'

// ── WebSocket Configuration ──────────────────────────────────
export const WS_PING_INTERVAL_MS = parseInt(import.meta.env.VITE_WS_PING_INTERVAL || '20000', 10)
export const WS_RECONNECT_MAX_ATTEMPTS = parseInt(import.meta.env.VITE_WS_RECONNECT_MAX || '10', 10)
export const WS_RECONNECT_DELAY_MS = parseInt(import.meta.env.VITE_WS_RECONNECT_DELAY || '3000', 10)

// ── UI Configuration ─────────────────────────────────────────
export const UI = {
  // Pagination
  DEFAULT_PAGE_SIZE: 50,
  MAX_PAGE_SIZE: 500,
  
  // Polling intervals (ms)
  POLLING: {
    HEALTH: 10000,
    STATS: 5000,
    HEATMAP: 3000,
    AGENT_RUNS: 15000,
  },
  
  // Timeouts
  TIMEOUTS: {
    IMAGE_LOAD: 5000,
    API_REQUEST: 10000,
  },
  
  // Thresholds for visual indicators
  THRESHOLDS: {
    FPS_GOOD: 20,
    FPS_WARNING: 10,
    VIOLATIONS_HIGH: 5,
  },
}

// ── Route Definitions ────────────────────────────────────────
export const ROUTES = {
  DASHBOARD: '/',
  CAMERAS: '/cameras',
  ALERTS: '/alerts',
  REPORTS: '/reports',
  SETTINGS: '/settings',
  LOGIN: '/login',
  WORKERS: '/workers',
  ZONES: '/zones',
}

// ── Violation Class Configuration ────────────────────────────
export const VIOLATION_CLASSES = {
  'no helmet': { 
    label: 'Missing Hard Hat', 
    severity: 'high',
    color: 'red',
    icon: '🪖',
  },
  'no vest': { 
    label: 'Missing Safety Vest', 
    severity: 'medium',
    color: 'orange',
    icon: '🦺',
  },
  'no hardhat': { 
    label: 'Missing Hard Hat', 
    severity: 'high',
    color: 'red',
    icon: '⛑️',
  },
  'no gloves': { 
    label: 'Missing Gloves', 
    severity: 'low',
    color: 'yellow',
    icon: '🧤',
  },
  'no goggles': { 
    label: 'Missing Eye Protection', 
    severity: 'medium',
    color: 'purple',
    icon: '🥽',
  },
  'no boots': { 
    label: 'Missing Safety Boots', 
    severity: 'low',
    color: 'amber',
    icon: '👢',
  },
  'no mask': { 
    label: 'Missing Respirator', 
    severity: 'high',
    color: 'pink',
    icon: '😷',
  },
  'no suit': { 
    label: 'Missing Protective Suit', 
    severity: 'high',
    color: 'rose',
    icon: '👨‍🚒',
  },
}

// ── Filter Options for Logs ──────────────────────────────────
export const LOG_FILTERS = [
  'all',
  'unacked',
  'no helmet',
  'no vest',
  'no hardhat',
  'no gloves',
  'no goggles',
  'no boots',
  'no mask',
  'no suit',
]

// ── Zone Types ───────────────────────────────────────────────
export const ZONE_TYPES = {
  danger: { label: 'Danger Zone', color: '#ef4444', icon: '⚠️' },
  restricted: { label: 'Restricted Area', color: '#f97316', icon: '🔒' },
  safe: { label: 'Safe Zone', color: '#22c55e', icon: '✅' },
}

// ── Alert Severity Levels ────────────────────────────────────
export const ALERT_LEVELS = {
  CRITICAL: { label: 'Critical', color: '#dc2626', priority: 1 },
  HIGH: { label: 'High', color: '#ea580c', priority: 2 },
  MEDIUM: { label: 'Medium', color: '#ca8a04', priority: 3 },
  LOW: { label: 'Low', color: '#16a34a', priority: 4 },
  NONE: { label: 'None', color: '#64748b', priority: 5 },
}

// ── Camera Layout Options ────────────────────────────────────
export const CAMERA_LAYOUTS = [
  { label: '1×1', cols: 1, max: 1 },
  { label: '2×2', cols: 2, max: 4 },
  { label: '3×3', cols: 3, max: 9 },
  { label: '4×4', cols: 4, max: 16 },
]

// ── Report Severity Colors ───────────────────────────────────
export const REPORT_SEVERITY_COLORS = {
  CRITICAL: { bg: '#7f1d1d', text: '#fca5a5', border: '#dc2626' },
  HIGH: { bg: '#7c2d12', text: '#fdba74', border: '#ea580c' },
  MEDIUM: { bg: '#713f12', text: '#fcd34d', border: '#ca8a04' },
  LOW: { bg: '#14532d', text: '#86efac', border: '#16a34a' },
}

// ── Helper Functions ─────────────────────────────────────────
/**
 * Format a timestamp for display
 * @param {string} isoString - ISO 8601 timestamp
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
    return isoString
  }
}

/**
 * Format a violation class name for display
 * @param {string} className - Machine-readable class name
 * @returns {string} Human-readable label
 */
export const formatViolationClass = (className) => {
  return VIOLATION_CLASSES[className]?.label || 
         className.replace(/^no\s+/i, 'Missing ').replace(/\b\w/g, l => l.toUpperCase())
}

/**
 * Get color configuration for a violation class
 * @param {string} className - Violation class name
 * @returns {Object} Color configuration
 */
export const getViolationColors = (className) => {
  const config = VIOLATION_CLASSES[className]
  return {
    bg: `${config?.color}-500/15`,
    text: `${config?.color}-400`,
    border: `${config?.color}-500/30`,
  }
}

/**
 * Validate an RTSP/HTTP URL
 * @param {string} url - URL to validate
 * @returns {boolean} True if valid
 */
export const isValidStreamUrl = (url) => {
  if (!url || !url.trim()) return false
  // Allow rtsp://, rtmp://, http://, https://, or numeric device index
  return /^(rtsp|rtmp|https?):\/\/[^ ]+$/.test(url.trim()) || /^\d+$/.test(url.trim())
}

/**
 * Sanitize a camera ID for safe usage
 * @param {string} id - Raw camera ID
 * @returns {string} Sanitized ID
 */
export const sanitizeCameraId = (id) => {
  if (!id) return ''
  // Allow only alphanumeric, underscore, hyphen
  return id.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 100)
}