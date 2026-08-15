/**
 * frontend/src/types.ts
 * Shared TypeScript types for the SafeGuardAI frontend.
 */

// ── Auth ────────────────────────────────────────────────────────
export interface AuthContextValue {
  isAuthenticated: boolean
  apiKey: string
  login: (key: string) => void
  logout: () => void
}

// ── WebSocket / Live Stream ─────────────────────────────────────
export interface StreamFrame {
  type: 'frame'
  timestamp: string
  frame_idx: number
  jpeg_b64: string
  active_tracks: number
  active_violations: number
  fps: number
}

export interface UseWebSocketOptions {
  pingMs?: number
  autoReconnect?: boolean
}

export interface UseWebSocketReturn {
  frame: StreamFrame | null
  connected: boolean
  connecting: boolean
  fps: number
  violations: number
  retryCount: number
  reconnect: () => void
  disconnect: () => void
}

// ── Violations ──────────────────────────────────────────────────
export interface ViolationEvent {
  id: number
  track_id: number
  class_name: string
  confidence: number
  zone_id: string | null
  camera_id: string | null
  bbox_x1: number
  bbox_y1: number
  bbox_x2: number
  bbox_y2: number
  frame_idx: number
  timestamp: string
  acknowledged: boolean
  notes: string | null
  severity?: string
  demo?: boolean
}

// ── Statistics ──────────────────────────────────────────────────
export interface DashboardStats {
  violations_today: number
  violations_this_week: number
  compliance_score: number
  active_workers: number
  high_risk_workers: number
  active_fire_alerts: number
  active_cameras: number
  pipeline_fps: number
  model_version: string
  uptime_hours: number
  timestamp: string
  demo?: boolean
  // from /stats endpoint
  total_violations?: number
  unacknowledged?: number
  by_zone?: Record<string, number>
  by_class?: Record<string, number>
}

// ── Workers ─────────────────────────────────────────────────────
export interface WorkerProfile {
  worker_id: string
  full_name: string
  department: string
  shift: string
  role: string
  risk_score: number
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  hr_alerted: boolean
  active: boolean
  enrolled: boolean
  photo_path: string | null
  created_at: string
  demo?: boolean
}

// ── Cameras ─────────────────────────────────────────────────────
export interface Camera {
  camera_id: string
  name: string
  url: string
  status: 'online' | 'offline' | 'error'
  fps: number
  resolution: string
  location: string
  demo?: boolean
}

// ── Zones ───────────────────────────────────────────────────────
export interface Zone {
  id: number
  zone_id: string
  zone_name: string
  zone_type: 'danger' | 'restricted' | 'safe'
  camera_id: string
  polygon_norm: [number, number][]
  required_ppe: string[]
  alert_enabled: boolean
  dwell_threshold_s: number
  color_hex: string
  active: boolean
  created_at: string
}

// ── Billing ─────────────────────────────────────────────────────
export interface BillingPlan {
  plan_id: string
  name: string
  pricing: {
    monthly_inr: number
    annual_inr: number
    annual_savings_pct: number
  }
  limits: {
    max_cameras: number
    max_sites: number
    max_users: number
  }
  features: string[]
}

// ── Agent / LangGraph ───────────────────────────────────────────
export interface AgentTraceStep {
  node: string
  timestamp: string
  details: Record<string, unknown>
}

export interface AgentRun {
  run_id: string
  violation_event: Partial<ViolationEvent>
  severity_score: number
  alert_level: 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  final_status: 'COMPLETE' | 'COMPLETE_WITH_ERRORS' | 'SKIPPED'
  trace_steps: AgentTraceStep[]
  created_at: string
}

// ── SHAP ────────────────────────────────────────────────────────
export interface SHAPResult {
  track_id: number
  class_name: string
  confidence: number
  saliency_b64: string
  top_regions: Array<{ zone: string; shap_value: number }>
}

// ── Reports ─────────────────────────────────────────────────────
export interface WeeklyReport {
  id: number
  report_date: string
  week_start: string
  week_end: string
  site_score: number
  prev_week_score: number
  score_delta: number
  total_violations: number
  total_workers: number
  high_risk_count: number
  violations_by_class: Record<string, number>
  violations_by_zone: Record<string, number>
  incident_summary: string
  pdf_path: string | null
  email_sent: boolean
  created_at: string
  has_pdf: boolean
  demo?: boolean
}

// ── Alerts ──────────────────────────────────────────────────────
export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'NONE'

export interface AlertConfig {
  enabled: boolean
  email_enabled: boolean
  whatsapp_enabled: boolean
  slack_enabled: boolean
  min_severity: AlertSeverity
  cooldown_seconds: number
}

// ── Component props helpers ─────────────────────────────────────
export interface WithChildren {
  children: React.ReactNode
}

export interface WithClassName {
  className?: string
}
