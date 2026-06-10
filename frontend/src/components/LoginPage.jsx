/**
 * LoginPage.jsx
 * Client-facing sign-in — email + password (admin / manager accounts).
 *
 * Note on auth: the backend currently uses API-key auth (no user table yet —
 * per-user JWT accounts are the documented v2 backend item in ARCHITECTURE_NOTES).
 * For the demo, known accounts map to the backend API key under the hood, so the
 * client-facing experience is a normal email/password login. The raw API key is
 * surfaced in Settings → API Access for programmatic integrations.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

// API base — '/api' (Vite proxy) in dev, the backend URL in production.
const API_BASE = import.meta.env.VITE_API_URL || '/api'

// Demo API key (the backend's dev key — used to authenticate demo accounts).
// In production, VITE_DEMO_API_KEY overrides this to match the deployed backend.
const DEMO_KEY = import.meta.env.VITE_DEMO_API_KEY
  || import.meta.env.VITE_API_KEY
  || '05ac3ecf4b9d6e8fc0a7f353d0d5023d83aa8b40bf4fb2ff277ab3f1eed5802a'

// Demo accounts → resolve to the backend API key. Replace with real JWT auth in prod.
const DEMO_ACCOUNTS = {
  'admin@safeguardai.io': {
    password: 'safeguard123', role: 'Administrator',
    key: DEMO_KEY, org: 'org-steel-india',
  },
  'manager@safeguardai.io': {
    password: 'safeguard123', role: 'Safety Manager',
    key: DEMO_KEY, org: 'org-steel-india',
  },
}

export default function LoginPage({ onLogin }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const completeLogin = async (key, org) => {
    // Confirm the key actually works against the backend before entering the app.
    try {
      const res = await fetch(`${API_BASE}/sites`, { headers: { Authorization: `Bearer ${key}` } })
      if (res.status === 401 || res.status === 403) {
        setError('Sign-in failed — your account could not be verified.')
        setLoading(false)
        return
      }
      if (org) localStorage.setItem('active_org_id', org)
      onLogin?.(key)
      navigate('/app')
    } catch {
      setError("Can't reach the server right now. Please try again in a moment.")
      setLoading(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    setError('')
    const acct = DEMO_ACCOUNTS[email.trim().toLowerCase()]
    if (!acct || acct.password !== password) {
      setError('Wrong email or password. Try again.')
      return
    }
    setLoading(true)
    completeLogin(acct.key, acct.org)
  }

  const handleDemo = () => {
    setLoading(true)
    setError('')
    completeLogin(DEMO_KEY, 'org-steel-india')
  }

  const valid = email.trim() && password

  return (
    <div className="min-h-screen bg-surface text-slate-100 flex">
      {/* ── Left: brand panel ── */}
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-hero-glow p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-grid-pattern [background-size:40px_40px] opacity-40" />
        <div className="relative">
          <button onClick={() => navigate('/')} className="flex items-center gap-2 mb-20 group">
            <span className="text-3xl group-hover:scale-110 transition-transform">🛡️</span>
            <span className="font-bold text-xl">SafeGuard<span className="text-brand-500">AI</span></span>
          </button>
          <h1 className="text-4xl font-black leading-tight mb-6">
            Your AI safety<br />
            <span className="bg-brand-gradient bg-clip-text text-transparent">inspector is ready.</span>
          </h1>
          <p className="text-slate-400 max-w-md">
            Sign in to monitor PPE compliance, fire hazards, permits, and worker
            attendance — all in real time, across every site.
          </p>
        </div>
        <div className="relative space-y-3">
          {['Real-time PPE detection on any camera', 'L1→L4 alert escalation', 'Digital permit-to-work + QR', 'Face-recognition attendance'].map(t => (
            <div key={t} className="flex items-center gap-3 text-sm text-slate-300">
              <span className="w-5 h-5 rounded-full bg-brand-500/20 border border-brand-500/40 flex items-center justify-center text-brand-400 text-xs">✓</span>
              {t}
            </div>
          ))}
        </div>
      </div>

      {/* ── Right: form ── */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          {/* mobile logo */}
          <button onClick={() => navigate('/')} className="lg:hidden flex items-center gap-2 mb-8 mx-auto">
            <span className="text-3xl">🛡️</span>
            <span className="font-bold text-xl">SafeGuard<span className="text-brand-500">AI</span></span>
          </button>

          <h2 className="text-2xl font-bold mb-1">Welcome back</h2>
          <p className="text-slate-400 text-sm mb-6">Sign in to your safety dashboard</p>

          {/* Demo access — single, one-click entry */}
          <div className="bg-brand-500/8 border border-brand-500/25 rounded-xl p-4 mb-5">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-brand-400 font-semibold text-sm">🎭 Just exploring?</span>
            </div>
            <p className="text-slate-400 text-xs mb-3">
              Jump straight into a fully-loaded demo — no signup, sample data across 8 industries.
            </p>
            <button
              type="button"
              onClick={handleDemo}
              disabled={loading}
              className="w-full bg-brand-gradient text-slate-900 font-bold py-2.5 rounded-lg hover:shadow-lg hover:shadow-brand-500/30 transition-all disabled:opacity-60"
            >
              {loading ? 'Loading demo…' : 'Launch Demo →'}
            </button>
          </div>

          <div className="flex items-center gap-3 mb-5">
            <div className="flex-1 h-px bg-surface-border" />
            <span className="text-slate-600 text-xs">or sign in with your account</span>
            <div className="flex-1 h-px bg-surface-border" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm text-slate-400 mb-1.5">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full bg-surface-raised border border-surface-border rounded-xl px-4 py-3 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none transition-colors"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm text-slate-400 mb-1.5">Password</label>
              <div className="relative">
                <input
                  id="password"
                  type={showPw ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="w-full bg-surface-raised border border-surface-border rounded-xl px-4 py-3 pr-16 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-brand-400 transition-colors"
                  aria-label={showPw ? 'Hide password' : 'Show password'}
                >
                  {showPw ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setError('Password resets are handled by your organization admin. Contact admin@safeguardai.io.')}
                className="text-xs text-slate-500 hover:text-brand-400 transition-colors"
              >
                Forgot password?
              </button>
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2.5 text-red-400 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !valid}
              className="w-full bg-surface-raised border border-surface-border text-slate-200 font-semibold py-3 rounded-xl hover:bg-surface-high hover:border-brand-500/40 transition-all disabled:opacity-50"
            >
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

          <p className="text-center text-slate-600 text-xs mt-6">
            New organization?{' '}
            <button
              onClick={() => navigate('/#pricing')}
              className="text-brand-400 hover:text-brand-300 underline"
            >
              View plans
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
