/**
 * frontend/src/App.jsx
 *
 * Root application component with routing, auth state, and layout.
 * FIXED: Imports from ./components/ (not ./pages/) to match your project structure
 */

import { useState, useEffect, useRef, useCallback, useContext, Suspense, lazy, createContext } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'

// Lazy-load components from ./components/ (your actual structure)
const AgentTracePanel = lazy(() => import('./components/AgentTracePanel'))
const AlertConfigPanel = lazy(() => import('./components/AlertConfigPanel'))
const AnalyticsCharts = lazy(() => import('./components/AnalyticsCharts'))
const CameraGrid = lazy(() => import('./components/CameraGrid'))
const ChatPanel = lazy(() => import('./components/ChatPanel'))
const FireAlertOverlay = lazy(() => import('./components/FireAlertOverlay'))
const HeatmapPanel = lazy(() => import('./components/HeatmapPanel'))
const LiveFeed = lazy(() => import('./components/LiveFeed'))
const MLOpsPanel = lazy(() => import('./components/MLOpsPanel'))
const PoseHazardPanel = lazy(() => import('./components/PoseHazardPanel'))
const ProximityPanel = lazy(() => import('./components/ProximityPanel'))
const ReportHistory = lazy(() => import('./components/ReportHistory'))
const SHAPModal = lazy(() => import('./components/SHAPModal'))
const StatCards = lazy(() => import('./components/StatCards'))
const StatusBar = lazy(() => import('./components/StatusBar'))
const ViolationLog = lazy(() => import('./components/ViolationLog'))
const WeeklyReportPanel = lazy(() => import('./components/WeeklyReportPanel'))
const WorkerProfilePage = lazy(() => import('./components/WorkerProfilePage'))
const ZoneAlertBanner = lazy(() => import('./components/ZoneAlertBanner'))
const ZoneDrawer = lazy(() => import('./components/ZoneDrawer'))
// New feature components
const DemoBanner = lazy(() => import('./components/DemoBanner'))
const DarkModeToggle = lazy(() => import('./components/DarkModeToggle'))
const ExportButton = lazy(() => import('./components/ExportButton'))
const WebhookConfigPanel = lazy(() => import('./components/WebhookConfigPanel'))
const CameraConfigPanel = lazy(() => import('./components/CameraConfigPanel'))
const OnboardingWizard = lazy(() => import('./components/OnboardingWizard'))
const AuditLogPanel = lazy(() => import('./components/AuditLogPanel'))
// Enterprise SaaS panels
const EscalationPanel = lazy(() => import('./components/EscalationPanel'))
const AttendancePanel = lazy(() => import('./components/AttendancePanel'))
const PermitPanel = lazy(() => import('./components/PermitPanel'))
const IndustryPPEPanel = lazy(() => import('./components/IndustryPPEPanel'))
const OrganizationPanel = lazy(() => import('./components/OrganizationPanel'))
const BillingPanel = lazy(() => import('./components/BillingPanel'))
const ApiAccessPanel = lazy(() => import('./components/ApiAccessPanel'))
// Client-facing pages
const LandingPage = lazy(() => import('./components/LandingPage'))
const LoginPage = lazy(() => import('./components/LoginPage'))

// Hooks
import { useWebSocket } from './hooks/useWebSocket'

// Constants
import { ROUTES, API_KEY_STORAGE_KEY as AUTH_STORAGE_KEY } from './constants'

// Full enterprise ErrorBoundary with per-panel isolation, error ID, dev stack trace
import ErrorBoundary from './components/ErrorBoundary'

// Toast notification system (replaces native alert())
import { ToastProvider } from './components/Toast'

// ── Simple Auth Context ─────────────────────────────────────
const AuthContext = createContext(null)

function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  // FIXED: Use sessionStorage instead of localStorage for API keys.
  // localStorage persists across tabs and browser sessions — an XSS attack on any tab
  // can steal it. sessionStorage is cleared when the tab closes, limiting exposure.
  const [apiKey, setApiKey] = useState(() => {
    try {
      return sessionStorage.getItem(AUTH_STORAGE_KEY) || ''
    } catch {
      return ''
    }
  })

  useEffect(() => {
    if (apiKey) {
      try {
        sessionStorage.setItem(AUTH_STORAGE_KEY, apiKey)
      } catch (e) {
        console.warn('Failed to persist API key:', e)
      }
    }
  }, [apiKey])

  const login = useCallback((key) => {
    setApiKey(key)
    setIsAuthenticated(true)
  }, [])

  const logout = useCallback(() => {
    setApiKey('')
    setIsAuthenticated(false)
    try {
      sessionStorage.removeItem(AUTH_STORAGE_KEY)
    } catch {}
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, apiKey, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

// ── Auth helpers ─────────────────────────────────────────────
function useAuth() {
  return useContext(AuthContext)
}

function RequireAuth({ children }) {
  const auth = useAuth()
  if (!auth?.isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return children
}

// ── Dashboard Shell (authenticated app) ──────────────────────
function DashboardShell() {
  const { logout } = useAuth()
  const [activeTab, setActiveTab] = useState('dashboard')
  const [showZoneDrawer, setShowZoneDrawer] = useState(false)
  const [showChat, setShowChat] = useState(false)

  const wsRef = useRef(null)
  // FIXED: useWebSocket already opens its own socket internally.
  // The duplicate createStreamSocket() in the useEffect below was opening a second
  // connection, sending every frame twice and wasting 2× server bandwidth.
  const { frame, connected: wsConnected, fps, violations } = useWebSocket({ pingMs: 20000 })

  // Navigation items
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'cameras', label: 'Cameras', icon: '📷' },
    { id: 'violations', label: 'Violations', icon: '⚠️' },
    { id: 'alerts', label: 'Alerts', icon: '🔔' },
    { id: 'reports', label: 'Reports', icon: '📄' },
    { id: 'analytics', label: 'Analytics', icon: '📈' },
    { id: 'mlops', label: 'MLOps', icon: '🤖' },
    { id: 'workers', label: 'Workers', icon: '👥' },
    { id: 'zones', label: 'Zones', icon: '🗺️' },
    { id: 'webhooks', label: 'Webhooks', icon: '🔗' },
    { id: 'audit',    label: 'Audit Log', icon: '📋' },
    // ── Enterprise SaaS ──
    { id: 'escalation',  label: 'Escalation', icon: '🚨' },
    { id: 'attendance',  label: 'Attendance',  icon: '👷' },
    { id: 'permits',     label: 'Permits',     icon: '📋' },
    { id: 'industry-ppe', label: 'Industry PPE', icon: '🏭' },
    { id: 'organizations', label: 'Organizations', icon: '🏢' },
    { id: 'billing',     label: 'Billing',     icon: '💳' },
    { id: 'settings', label: 'Settings', icon: '⚙️' },
  ]

  return (
          <div className="min-h-screen bg-surface text-slate-100 flex flex-col">

            {/* Onboarding wizard (first-time only) */}
            <Suspense fallback={null}>
              <OnboardingWizard />
            </Suspense>

            {/* Demo mode banner */}
            <Suspense fallback={null}>
              <DemoBanner />
            </Suspense>

            {/* Global status bar */}
            <StatusBar
              wsConnected={wsConnected}
              fps={fps}
              violations={violations}
            />

            {/* Fire emergency overlay */}
            <FireAlertOverlay wsRef={wsRef} />

            {/* Zone alert banner (when active) */}
            <ZoneAlertBanner />

            <div className="flex flex-1 overflow-hidden">
              
              {/* Sidebar Navigation */}
              <aside className="w-16 lg:w-56 bg-surface-raised border-r border-surface-border/60 flex flex-col">
                <div className="p-4 border-b border-surface-border/60">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🛡️</span>
                    <span className="font-bold text-sm hidden lg:block">SafeGuard<span className="text-brand-500">AI</span></span>
                  </div>
                  <div className="mt-2 hidden lg:block">
                    <Suspense fallback={null}>
                      <DarkModeToggle />
                    </Suspense>
                  </div>
                </div>

                <nav className="flex-1 overflow-y-auto py-2">
                  {navItems.map(item => (
                    <button
                      key={item.id}
                      onClick={() => setActiveTab(item.id)}
                      className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors
                        ${activeTab === item.id
                          ? 'bg-brand-500/15 text-brand-400 border-r-2 border-brand-500'
                          : 'text-slate-400 hover:bg-surface-high/50 hover:text-slate-200'
                        }`}
                    >
                      <span className="text-lg">{item.icon}</span>
                      <span className="hidden lg:block">{item.label}</span>
                    </button>
                  ))}
                </nav>

                {/* Zone toggle */}
                <button
                  onClick={() => setShowZoneDrawer(!showZoneDrawer)}
                  className={`p-4 border-t border-surface-border/60 text-sm flex items-center gap-2
                    ${showZoneDrawer ? 'bg-brand-500/15 text-brand-400' : 'text-slate-400 hover:bg-surface-high/50'}`}
                >
                  <span>🗺️</span>
                  <span className="hidden lg:block">Zones</span>
                </button>

                {/* Logout */}
                <button
                  onClick={logout}
                  className="p-4 border-t border-surface-border/60 text-sm flex items-center gap-2 text-slate-400 hover:bg-red-500/10 hover:text-red-400 transition-colors"
                >
                  <span>🚪</span>
                  <span className="hidden lg:block">Sign Out</span>
                </button>
              </aside>

              {/* Main Content Area */}
              <main className="flex-1 overflow-y-auto p-4 lg:p-6">
                <ErrorBoundary>
                <Suspense fallback={
                  <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-500"></div>
                  </div>
                }>
                  {/* Dashboard View */}
                  {activeTab === 'dashboard' && (
                    <div className="space-y-6">
                      <StatCards fps={fps} violations={violations} activeTracks={frame?.active_tracks || 0} />
                      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                        <div className="xl:col-span-2">
                          <LiveFeed frame={frame} connected={wsConnected} />
                        </div>
                        <div className="space-y-6">
                          <HeatmapPanel />
                          <AnalyticsCharts />
                        </div>
                      </div>
                      <ViolationLog />
                    </div>
                  )}

                  {/* Cameras View */}
                  {activeTab === 'cameras' && (
                    <div className="space-y-6">
                      <CameraGrid wsRef={wsRef} />
                      <Suspense fallback={null}>
                        <CameraConfigPanel />
                      </Suspense>
                    </div>
                  )}

                  {/* Violations View */}
                  {activeTab === 'violations' && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <h2 className="text-lg font-semibold text-slate-100">Violation Events</h2>
                        <div className="flex gap-2 flex-wrap">
                          <Suspense fallback={null}>
                            <ExportButton endpoint="/export/violations.csv" label="Export CSV" variant="csv" />
                            <ExportButton endpoint="/export/violations.json" label="Export JSON" variant="json" />
                          </Suspense>
                        </div>
                      </div>
                      <ViolationLog />
                    </div>
                  )}

                  {/* Alerts View */}
                  {activeTab === 'alerts' && <AlertConfigPanel />}

                  {/* Reports View */}
                  {activeTab === 'reports' && (
                    <div className="space-y-6">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <h2 className="text-lg font-semibold text-slate-100">Reports & Compliance</h2>
                        <div className="flex gap-2 flex-wrap">
                          <Suspense fallback={null}>
                            <ExportButton endpoint="/export/reports.csv" label="Export Reports" variant="csv" />
                            <ExportButton endpoint="/export/workers.csv" label="Export Workers" variant="csv" />
                            <ExportButton endpoint="/export/zone-analytics.csv" label="Zone Analytics" variant="csv" />
                          </Suspense>
                        </div>
                      </div>
                      <WeeklyReportPanel />
                      <ReportHistory />
                    </div>
                  )}

                  {/* Analytics View */}
                  {activeTab === 'analytics' && <AnalyticsCharts />}

                  {/* MLOps View */}
                  {activeTab === 'mlops' && <MLOpsPanel />}

                  {/* Workers View */}
                  {activeTab === 'workers' && <WorkerProfilePage />}

                  {/* Zones View */}
                  {activeTab === 'zones' && (
                    <div className="flex gap-6">
                      <div className="flex-1">
                        <CameraGrid wsRef={wsRef} />
                      </div>
                      <div className="w-80 hidden xl:block">
                        <ZoneDrawer onClose={() => {}} />
                      </div>
                    </div>
                  )}

                  {/* Webhooks View */}
                  {activeTab === 'webhooks' && (
                    <div className="max-w-3xl">
                      <Suspense fallback={<div className="text-slate-400">Loading…</div>}>
                        <WebhookConfigPanel />
                      </Suspense>
                    </div>
                  )}

                  {/* Audit Log View */}
                  {activeTab === 'audit' && (
                    <div className="max-w-5xl">
                      <Suspense fallback={<div className="text-slate-400">Loading…</div>}>
                        <AuditLogPanel />
                      </Suspense>
                    </div>
                  )}

                  {/* ── Enterprise SaaS Panels ─────────────────────── */}

                  {/* Alert Escalation Matrix */}
                  {activeTab === 'escalation' && (
                    <div className="max-w-4xl">
                      <ErrorBoundary>
                        <Suspense fallback={<div className="text-slate-400">Loading…</div>}>
                          <EscalationPanel />
                        </Suspense>
                      </ErrorBoundary>
                    </div>
                  )}

                  {/* Attendance & Headcount */}
                  {activeTab === 'attendance' && (
                    <div className="max-w-4xl">
                      <ErrorBoundary>
                        <Suspense fallback={<div className="text-slate-400">Loading…</div>}>
                          <AttendancePanel />
                        </Suspense>
                      </ErrorBoundary>
                    </div>
                  )}

                  {/* Permit to Work */}
                  {activeTab === 'permits' && (
                    <div className="max-w-4xl">
                      <ErrorBoundary>
                        <Suspense fallback={<div className="text-slate-400">Loading…</div>}>
                          <PermitPanel />
                        </Suspense>
                      </ErrorBoundary>
                    </div>
                  )}

                  {/* Industry PPE Profiles */}
                  {activeTab === 'industry-ppe' && (
                    <div className="max-w-5xl">
                      <ErrorBoundary>
                        <Suspense fallback={<div className="text-slate-400">Loading…</div>}>
                          <IndustryPPEPanel />
                        </Suspense>
                      </ErrorBoundary>
                    </div>
                  )}

                  {/* Organizations (Super Admin) */}
                  {activeTab === 'organizations' && (
                    <div className="max-w-4xl">
                      <ErrorBoundary>
                        <Suspense fallback={<div className="text-slate-400">Loading…</div>}>
                          <OrganizationPanel />
                        </Suspense>
                      </ErrorBoundary>
                    </div>
                  )}

                  {/* Billing */}
                  {activeTab === 'billing' && (
                    <div className="max-w-5xl">
                      <ErrorBoundary>
                        <Suspense fallback={<div className="text-slate-400">Loading…</div>}>
                          <BillingPanel />
                        </Suspense>
                      </ErrorBoundary>
                    </div>
                  )}

                  {/* Settings View */}
                  {activeTab === 'settings' && (
                    <div className="max-w-2xl space-y-6">
                      <Suspense fallback={null}>
                        <ApiAccessPanel />
                      </Suspense>
                      <AlertConfigPanel />
                      <div className="pt-4 border-t border-slate-800/60">
                        <h3 className="text-sm font-semibold text-slate-300 mb-3">Theme</h3>
                        <Suspense fallback={null}>
                          <DarkModeToggle />
                        </Suspense>
                      </div>
                    </div>
                  )}

                  {/* Agent Trace Panel (accessible from violations) */}
                  {activeTab === 'violations' && (
                    <div className="mt-6">
                      <AgentTracePanel />
                    </div>
                  )}

                  {/* Pose Hazards Panel */}
                  {activeTab === 'dashboard' && (
                    <div className="mt-6">
                      <PoseHazardPanel wsRef={wsRef} />
                    </div>
                  )}

                  {/* Proximity Panel */}
                  {activeTab === 'dashboard' && (
                    <div className="mt-6">
                      <ProximityPanel wsRef={wsRef} />
                    </div>
                  )}
                </Suspense>
                </ErrorBoundary>
              </main>

              {/* Zone Drawer (slide-over) */}
              {showZoneDrawer && (
                <div className="fixed inset-y-0 right-0 w-80 bg-surface-raised border-l border-surface-border/60 shadow-xl z-30">
                  <ZoneDrawer onClose={() => setShowZoneDrawer(false)} />
                </div>
              )}
            </div>

            {/* Chat toggle button */}
            <button
              onClick={() => setShowChat(!showChat)}
              className="fixed bottom-6 right-6 w-14 h-14 bg-brand-gradient
                         text-slate-900 rounded-full shadow-lg shadow-brand-500/30 flex items-center justify-center
                         transition-transform hover:scale-105 z-40"
              aria-label={showChat ? 'Close chat' : 'Open safety assistant'}
            >
              {showChat ? '✕' : '💬'}
            </button>

            {/* Chat panel */}
            {showChat && (
              <ChatPanel 
                isOpen={showChat} 
                onClose={() => setShowChat(false)} 
              />
            )}

            {/* SHAP Modal (rendered when needed) */}
            {/* Note: SHAPModal is triggered from ViolationLog via callback */}
          </div>
  )
}

// ── Routes ───────────────────────────────────────────────────
function AppRoutes() {
  const { login } = useAuth()
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-500" />
      </div>
    }>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage onLogin={login} />} />
        <Route path="/app/*" element={
          <RequireAuth><DashboardShell /></RequireAuth>
        } />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

// ── Main App Component ───────────────────────────────────────
export default function App() {
  // Query client
  const queryClient = useRef(
    new QueryClient({
      defaultOptions: {
        queries: {
          retry: 2,
          retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
          staleTime: 5000,
          refetchOnWindowFocus: false,
        },
      },
    })
  ).current

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter basename={import.meta.env.BASE_URL}>
            <AppRoutes />
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}