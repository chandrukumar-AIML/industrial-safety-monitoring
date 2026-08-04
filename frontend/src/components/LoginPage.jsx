import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_URL || ''

export default function LoginPage({ onLogin }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Sign-in failed. Check your credentials.')
        setLoading(false)
        return
      }
      if (data.org_id) localStorage.setItem('active_org_id', data.org_id)
      onLogin?.(data.access_token)
    } catch {
      setError("Can't reach the server right now. Please try again in a moment.")
      setLoading(false)
    }
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
                onClick={() => setError('Password resets are handled by your organization admin.')}
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
              className="w-full bg-brand-gradient text-slate-900 font-bold py-3 rounded-xl hover:shadow-lg hover:shadow-brand-500/30 transition-all disabled:opacity-50"
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
