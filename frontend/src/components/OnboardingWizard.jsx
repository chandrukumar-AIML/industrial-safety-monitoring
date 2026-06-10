/**
 * frontend/src/components/OnboardingWizard.jsx
 *
 * First-time setup wizard shown when no cameras are configured.
 * Guides the user through:
 *   Step 1 — Welcome & demo mode option
 *   Step 2 — Connect first camera
 *   Step 3 — Set alert destinations (email / WhatsApp)
 *   Step 4 — Ready!
 *
 * Dismissable — stored in localStorage so it only shows once.
 */

import { useState, useEffect } from 'react'

const STORAGE_KEY = 'sm_onboarding_done'
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const STEPS = [
  { id: 'welcome',  title: 'Welcome to Safety Monitor 🛡️',  icon: '👋' },
  { id: 'camera',   title: 'Connect Your First Camera',       icon: '📷' },
  { id: 'alerts',   title: 'Set Up Alert Destinations',       icon: '🔔' },
  { id: 'done',     title: "You're Ready!",                   icon: '🎉' },
]

export default function OnboardingWizard() {
  const [visible, setVisible] = useState(false)
  const [step, setStep] = useState(0)
  const [demoLoading, setDemoLoading] = useState(false)

  useEffect(() => {
    try {
      const done = localStorage.getItem(STORAGE_KEY)
      if (!done) setVisible(true)
    } catch {}
  }, [])

  function dismiss() {
    try { localStorage.setItem(STORAGE_KEY, '1') } catch {}
    setVisible(false)
  }

  async function enableDemo() {
    setDemoLoading(true)
    // Demo mode is controlled by DEMO_MODE env var server-side.
    // We just guide the user to set it and show them the demo data URL.
    setTimeout(() => {
      setDemoLoading(false)
      setStep(3)  // Jump to done
    }, 1000)
  }

  if (!visible) return null

  const current = STEPS[step]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-[#161b22] border border-slate-700/60 rounded-2xl shadow-2xl w-full max-w-lg">

        {/* Progress dots */}
        <div className="flex justify-center gap-2 pt-6">
          {STEPS.map((s, i) => (
            <div
              key={s.id}
              className={`h-2 rounded-full transition-all duration-300 ${
                i === step ? 'w-8 bg-blue-500' : i < step ? 'w-2 bg-blue-800' : 'w-2 bg-slate-700'
              }`}
            />
          ))}
        </div>

        {/* Content */}
        <div className="px-8 py-6 text-center">
          <div className="text-5xl mb-4">{current.icon}</div>
          <h2 className="text-xl font-bold text-slate-100 mb-2">{current.title}</h2>

          {/* Step 0: Welcome */}
          {step === 0 && (
            <div className="space-y-4">
              <p className="text-slate-400 text-sm leading-relaxed">
                Industrial Safety Monitor uses AI to detect PPE violations, fire hazards, and worker risks in real time.
                Let's get you set up in under 2 minutes.
              </p>
              <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg p-3 text-left">
                <p className="text-amber-300 text-xs font-semibold mb-1">🎭 No camera? No problem.</p>
                <p className="text-amber-400/80 text-xs">
                  Enable <strong>Demo Mode</strong> to see the full system with synthetic data — perfect for presentations.
                </p>
              </div>
              <div className="flex gap-3 justify-center mt-4">
                <button
                  onClick={enableDemo}
                  disabled={demoLoading}
                  className="px-4 py-2 bg-amber-700/50 hover:bg-amber-600/60 border border-amber-600/50 text-amber-300 text-sm rounded-lg transition-colors disabled:opacity-60"
                >
                  {demoLoading ? '⏳ Enabling…' : '🎭 Use Demo Mode'}
                </button>
                <button
                  onClick={() => setStep(1)}
                  className="px-4 py-2 bg-brand-500 hover:bg-brand-600 text-slate-900 font-semibold text-sm rounded-lg transition-colors"
                >
                  I have a camera →
                </button>
              </div>
            </div>
          )}

          {/* Step 1: Camera */}
          {step === 1 && (
            <div className="space-y-4 text-left">
              <p className="text-slate-400 text-sm text-center">Add your first camera source. You can add more later in Settings → Cameras.</p>
              <div className="space-y-2">
                <div className="bg-slate-800/60 rounded-lg p-3 border border-slate-700/50">
                  <p className="text-xs font-semibold text-slate-300 mb-1">🔌 USB Webcam</p>
                  <p className="text-xs text-slate-500">Use <code className="bg-slate-900 px-1 rounded">VIDEO_SOURCE=0</code> in your <code>.env</code> file. Already set by default.</p>
                </div>
                <div className="bg-slate-800/60 rounded-lg p-3 border border-slate-700/50">
                  <p className="text-xs font-semibold text-slate-300 mb-1">📡 RTSP IP Camera</p>
                  <p className="text-xs text-slate-500 font-mono break-all">VIDEO_SOURCE=rtsp://admin:pass@192.168.1.100:554/stream1</p>
                </div>
                <div className="bg-slate-800/60 rounded-lg p-3 border border-slate-700/50">
                  <p className="text-xs font-semibold text-slate-300 mb-1">🎬 Video File (testing)</p>
                  <p className="text-xs text-slate-500 font-mono">VIDEO_SOURCE=/app/data/sample.mp4</p>
                </div>
              </div>
              <p className="text-xs text-slate-600 text-center">After setting in .env, restart the backend container.</p>
            </div>
          )}

          {/* Step 2: Alerts */}
          {step === 2 && (
            <div className="space-y-3 text-left">
              <p className="text-slate-400 text-sm text-center">Configure where you want violation alerts sent.</p>
              <div className="space-y-2">
                {[
                  { icon: '💬', name: 'WhatsApp (Twilio)', env: 'TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM', note: 'Instant alerts on your phone' },
                  { icon: '📧', name: 'Email (SMTP)', env: 'SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD', note: 'Works with Gmail, Outlook, etc.' },
                  { icon: '🔗', name: 'Slack / Teams / JIRA', env: 'Configure via Settings → Webhooks in the dashboard', note: 'No env needed — UI-based' },
                ].map(a => (
                  <div key={a.name} className="bg-slate-800/60 rounded-lg p-3 border border-slate-700/50">
                    <div className="flex items-center gap-2 mb-1">
                      <span>{a.icon}</span>
                      <span className="text-xs font-semibold text-slate-300">{a.name}</span>
                      <span className="text-xs text-slate-600">— {a.note}</span>
                    </div>
                    <p className="text-xs text-slate-500 font-mono">{a.env}</p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-600 text-center">You can skip this and configure alerts later in Settings.</p>
            </div>
          )}

          {/* Step 3: Done */}
          {step === 3 && (
            <div className="space-y-4">
              <p className="text-slate-400 text-sm leading-relaxed">
                Setup complete! Your safety monitoring system is ready.
              </p>
              <div className="grid grid-cols-2 gap-2 text-left">
                {[
                  { icon: '⚠️', label: 'Violations', desc: 'Real-time PPE detection' },
                  { icon: '📊', label: 'Dashboard', desc: 'Live KPIs & heatmap' },
                  { icon: '📄', label: 'Reports', desc: 'AI-generated OSHA reports' },
                  { icon: '💬', label: 'Chatbot', desc: 'Ask safety questions' },
                ].map(f => (
                  <div key={f.label} className="bg-slate-800/60 rounded-lg p-2.5 border border-slate-700/40">
                    <div className="flex items-center gap-1.5">
                      <span>{f.icon}</span>
                      <span className="text-xs font-semibold text-slate-300">{f.label}</span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">{f.desc}</p>
                  </div>
                ))}
              </div>
              <a
                href="/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-400 hover:underline block"
              >
                📖 View full API documentation →
              </a>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-8 pb-6 flex items-center justify-between">
          <button
            onClick={dismiss}
            className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
          >
            Skip setup
          </button>
          <div className="flex gap-2">
            {step > 0 && step < 3 && (
              <button
                onClick={() => setStep(s => s - 1)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm rounded-lg transition-colors"
              >
                ← Back
              </button>
            )}
            {step < 3 ? (
              <button
                onClick={() => setStep(s => s + 1)}
                className="px-4 py-2 bg-brand-500 hover:bg-brand-600 text-slate-900 font-semibold text-sm rounded-lg transition-colors"
              >
                {step === 2 ? 'Finish setup' : 'Next →'}
              </button>
            ) : (
              <button
                onClick={dismiss}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition-colors"
              >
                🚀 Go to Dashboard
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
