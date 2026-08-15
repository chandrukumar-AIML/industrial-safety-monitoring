/**
 * LandingPage.jsx
 * Client-facing marketing landing page.
 * Hi-Vis Amber theme — distinct from blue competitors.
 */
import { useNavigate } from 'react-router-dom'

const FEATURES = [
  { icon: '⛑️', title: 'PPE Detection', desc: 'Real-time helmet, vest, gloves, boots, goggles & mask detection on any camera feed.' },
  { icon: '🔥', title: 'Fire & Smoke', desc: 'Early fire and smoke detection with instant multi-channel alerts.' },
  { icon: '🚨', title: 'Alert Escalation', desc: 'L1→L4 escalation matrix. Supervisor → Safety Officer → Plant Head → Emergency.' },
  { icon: '📋', title: 'Permit-to-Work', desc: 'Digital PTW with QR validation. 9 work types, time-bounded, paperless.' },
  { icon: '👷', title: 'Attendance & Muster', desc: 'Face-recognition headcount, live on-site count, emergency muster drills.' },
  { icon: '🏭', title: 'Industry PPE Profiles', desc: '8 industries, 23 zone configs. OSHA / IS compliance built-in.' },
  { icon: '🤖', title: 'AI Incident Reports', desc: 'Auto-generated OSHA-grade narratives. LLM-powered, zero manual typing.' },
  { icon: '📊', title: 'Proximity & Pose', desc: 'Human-machine distance alerts + unsafe posture / fall detection.' },
]

const INDUSTRIES = [
  { icon: '🏗️', name: 'Construction' }, { icon: '⚙️', name: 'Steel' },
  { icon: '🛢️', name: 'Oil & Gas' }, { icon: '💊', name: 'Pharma' },
  { icon: '📦', name: 'Warehouse' }, { icon: '⚡', name: 'Power Plant' },
  { icon: '🚢', name: 'Shipbuilding' }, { icon: '⛏️', name: 'Mining' },
]

const COMPARISON = [
  { feature: 'PPE Detection',        us: true,  them: true },
  { feature: 'Permit-to-Work',       us: true,  them: false },
  { feature: 'Worker Attendance',    us: true,  them: false },
  { feature: 'India Billing (UPI)',  us: true,  them: false },
  { feature: 'Self-host option',     us: true,  them: false },
  { feature: 'Multi-tenant SaaS',    us: true,  them: true },
  { feature: 'Pricing (per month)',  us: '₹4,999', them: '$300–2,000' },
]

const PLANS = [
  { name: 'Starter',    price: '₹4,999',  badge: '🥉', features: ['5 cameras', '1 site', '10 users', 'PPE + Email alerts', '90-day retention'] },
  { name: 'Growth',     price: '₹14,999', badge: '🥈', popular: true, features: ['20 cameras', '3 sites', '25 users', 'All detection + WhatsApp', 'Permits + Attendance', '1-year retention'] },
  { name: 'Enterprise', price: '₹39,999', badge: '🥇', features: ['Unlimited cameras', 'Unlimited sites', 'Unlimited users', 'Everything + Escalation', 'Dedicated support', 'On-prem option'] },
]

function Nav({ navigate }) {
  return (
    <nav className="fixed top-0 inset-x-0 z-50 backdrop-blur-md bg-surface/80 border-b border-surface-border/40">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🛡️</span>
          <span className="font-bold text-lg text-white">SafeGuard<span className="text-brand-500">AI</span></span>
        </div>
        <div className="hidden md:flex items-center gap-8 text-sm text-slate-300">
          <a href="#features" className="hover:text-brand-400 transition-colors">Features</a>
          <a href="#industries" className="hover:text-brand-400 transition-colors">Industries</a>
          <a href="#compare" className="hover:text-brand-400 transition-colors">Why Us</a>
          <a href="#pricing" className="hover:text-brand-400 transition-colors">Pricing</a>
        </div>
        <button
          onClick={() => navigate('/login')}
          className="bg-brand-gradient text-slate-900 font-semibold text-sm px-5 py-2 rounded-lg hover:shadow-lg hover:shadow-brand-500/30 transition-all"
        >
          Sign In →
        </button>
      </div>
    </nav>
  )
}

/**
 * HeroMockup — a stylized preview of the live dashboard, built from the design
 * system (not a screenshot). Shows the product's shape: KPI cards, an annotated
 * live feed with a detection box, and a violations-by-class chart.
 */
function HeroMockup() {
  const bars = [70, 64, 82, 58, 74, 48, 66]
  const barColors = ['#ef4444', '#f97316', '#f59e0b', '#10b981', '#a855f7', '#06b6d4', '#fbbf24']
  return (
    <div className="mt-20 max-w-4xl mx-auto">
      <div className="relative rounded-2xl border border-surface-border/70 bg-surface-raised shadow-2xl shadow-black/40 overflow-hidden">
        {/* Browser chrome */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-surface-border/60 bg-surface-high/30">
          <span className="w-3 h-3 rounded-full bg-red-500/70" />
          <span className="w-3 h-3 rounded-full bg-amber-400/70" />
          <span className="w-3 h-3 rounded-full bg-emerald-500/70" />
          <span className="ml-3 text-xs text-slate-500 font-mono">app.safeguardai.io/dashboard</span>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Live
          </span>
        </div>

        {/* Body */}
        <div className="p-4 grid grid-cols-3 gap-3 text-left">
          {/* KPI cards */}
          {[['373', 'Violations', 'text-red-400'], ['8', 'On Site', 'text-emerald-400'], ['87%', 'Compliance', 'text-brand-400']].map(([n, l, c]) => (
            <div key={l} className="bg-surface border border-surface-border/50 rounded-xl p-3">
              <div className={`text-2xl font-black ${c}`}>{n}</div>
              <div className="text-[11px] text-slate-500 mt-0.5">{l}</div>
            </div>
          ))}

          {/* Live feed with detection box */}
          <div className="col-span-2 bg-surface border border-surface-border/50 rounded-xl p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-slate-400">📹 Welding Bay — Cam 03</span>
            </div>
            <div className="relative h-32 rounded-lg bg-gradient-to-br from-slate-800 to-slate-900 overflow-hidden">
              {/* worker silhouette */}
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-10 h-24 bg-slate-700/70 rounded-t-2xl" />
              {/* detection box */}
              <div className="absolute top-3 left-1/2 -translate-x-1/2 w-16 h-10 border-2 border-red-500 rounded">
                <span className="absolute -top-5 left-0 bg-red-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded">
                  NO HELMET 94%
                </span>
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="bg-surface border border-surface-border/50 rounded-xl p-3">
            <div className="text-[11px] text-slate-500 mb-2">Violations / class</div>
            <div className="flex items-end gap-1 h-28">
              {bars.map((h, i) => (
                <div key={i} className="flex-1 rounded-t" style={{ height: `${h}%`, background: barColors[i] }} />
              ))}
            </div>
          </div>
        </div>
      </div>
      <p className="text-center text-slate-600 text-xs mt-3">Live demo · synthetic data · no signup required</p>
    </div>
  )
}

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-surface text-slate-100 overflow-x-hidden">
      <Nav navigate={navigate} />

      {/* ── HERO ── */}
      <section className="relative pt-32 pb-20 px-6 bg-hero-glow">
        <div className="absolute inset-0 bg-grid-pattern [background-size:40px_40px] opacity-40" />
        <div className="relative max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-brand-500/10 border border-brand-500/30 rounded-full px-4 py-1.5 mb-6">
            <span className="w-2 h-2 rounded-full bg-brand-500 animate-pulse" />
            <span className="text-brand-300 text-xs font-medium">AI-Powered Industrial Safety · Made in India 🇮🇳</span>
          </div>
          <h1 className="text-5xl md:text-7xl font-black tracking-tight mb-6 leading-tight">
            Stop accidents<br />
            <span className="bg-brand-gradient bg-clip-text text-transparent">before they happen.</span>
          </h1>
          <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto mb-10">
            Turn any CCTV camera into an AI safety inspector. Detect PPE violations,
            fire hazards, and unsafe behavior in real time — across 8 industries.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => navigate('/login')}
              className="bg-brand-gradient text-slate-900 font-bold px-8 py-4 rounded-xl text-lg hover:shadow-xl hover:shadow-brand-500/40 transition-all hover:-translate-y-0.5"
            >
              🚀 Launch Live Demo
            </button>
            <a
              href="#features"
              className="border border-surface-border text-slate-300 font-semibold px-8 py-4 rounded-xl text-lg hover:bg-surface-raised transition-all"
            >
              See Features
            </a>
          </div>
          {/* Stat strip */}
          <div className="grid grid-cols-3 gap-6 max-w-2xl mx-auto mt-16">
            {[['8', 'Industries'], ['60+', 'API Endpoints'], ['99.2%', 'mAP Accuracy']].map(([n, l]) => (
              <div key={l}>
                <div className="text-3xl md:text-4xl font-black text-brand-500">{n}</div>
                <div className="text-slate-500 text-sm mt-1">{l}</div>
              </div>
            ))}
          </div>

          {/* ── Product mockup ── */}
          <HeroMockup />
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section id="features" className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-3">
            One platform. <span className="text-brand-500">Total site safety.</span>
          </h2>
          <p className="text-slate-400 text-center mb-14 max-w-xl mx-auto">
            Everything a safety officer needs — no extra hardware, works with existing cameras.
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {FEATURES.map(f => (
              <div key={f.title} className="bg-surface-raised border border-surface-border/60 rounded-2xl p-6 hover:border-brand-500/40 hover:-translate-y-1 transition-all group">
                <div className="text-4xl mb-4 group-hover:scale-110 transition-transform">{f.icon}</div>
                <h3 className="font-bold text-white mb-2">{f.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── INDUSTRIES ── */}
      <section id="industries" className="py-16 px-6 bg-surface-raised/30">
        <div className="max-w-5xl mx-auto text-center">
          <h2 className="text-2xl md:text-3xl font-bold mb-10">Built for heavy industry</h2>
          <div className="grid grid-cols-4 md:grid-cols-8 gap-4">
            {INDUSTRIES.map(i => (
              <div key={i.name} className="flex flex-col items-center gap-2">
                <div className="w-16 h-16 rounded-2xl bg-surface-raised border border-surface-border/60 flex items-center justify-center text-3xl hover:border-brand-500/50 transition-colors">
                  {i.icon}
                </div>
                <span className="text-xs text-slate-400">{i.name}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── COMPARISON ── */}
      <section id="compare" className="py-20 px-6">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-3">
            Why <span className="text-brand-500">SafeGuardAI</span>?
          </h2>
          <p className="text-slate-400 text-center mb-12">
            Global competitors charge in dollars and skip India-specific workflows.
          </p>
          <div className="bg-surface-raised border border-surface-border/60 rounded-2xl overflow-hidden">
            <div className="grid grid-cols-3 bg-surface-high/40 text-sm font-semibold">
              <div className="p-4 text-slate-400">Capability</div>
              <div className="p-4 text-center text-brand-400">SafeGuardAI</div>
              <div className="p-4 text-center text-slate-500">Others</div>
            </div>
            {COMPARISON.map((row, i) => (
              <div key={row.feature} className={`grid grid-cols-3 text-sm ${i % 2 ? 'bg-surface/40' : ''}`}>
                <div className="p-4 text-slate-300">{row.feature}</div>
                <div className="p-4 text-center font-medium">
                  {row.us === true ? <span className="text-brand-500">✓</span> : <span className="text-brand-400">{row.us}</span>}
                </div>
                <div className="p-4 text-center text-slate-500">
                  {row.them === true ? '✓' : row.them === false ? <span className="text-slate-700">✕</span> : row.them}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="pricing" className="py-20 px-6 bg-surface-raised/30">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-3">Simple, India-first pricing</h2>
          <p className="text-slate-400 text-center mb-14">Pay in ₹ via UPI, cards, or net banking. No dollar surprises.</p>
          <div className="grid md:grid-cols-3 gap-6">
            {PLANS.map(p => (
              <div key={p.name} className={`relative rounded-2xl p-6 flex flex-col ${
                p.popular
                  ? 'bg-surface-raised border-2 border-brand-500 shadow-xl shadow-brand-500/10'
                  : 'bg-surface-raised border border-surface-border/60'
              }`}>
                {p.popular && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-brand-gradient text-slate-900 text-xs font-bold px-3 py-1 rounded-full">
                    MOST POPULAR
                  </span>
                )}
                <div className="text-3xl mb-2">{p.badge}</div>
                <h3 className="font-bold text-xl text-white">{p.name}</h3>
                <div className="mt-3 mb-5">
                  <span className="text-4xl font-black text-white">{p.price}</span>
                  <span className="text-slate-500 text-sm">/mo</span>
                </div>
                <ul className="flex-1 space-y-2 mb-6">
                  {p.features.map(f => (
                    <li key={f} className="flex items-start gap-2 text-sm text-slate-300">
                      <span className="text-brand-500 mt-0.5">✓</span> {f}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => navigate('/login')}
                  className={`w-full py-3 rounded-xl font-bold text-sm transition-all ${
                    p.popular
                      ? 'bg-brand-gradient text-slate-900 hover:shadow-lg hover:shadow-brand-500/30'
                      : 'border border-surface-border text-slate-200 hover:bg-surface-high'
                  }`}
                >
                  Get Started
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-24 px-6">
        <div className="max-w-3xl mx-auto text-center bg-brand-gradient rounded-3xl p-12 relative overflow-hidden">
          <div className="absolute inset-0 bg-grid-pattern [background-size:30px_30px] opacity-20" />
          <div className="relative">
            <h2 className="text-3xl md:text-4xl font-black text-slate-900 mb-4">
              Ready to make your site safer?
            </h2>
            <p className="text-slate-800 mb-8 text-lg">
              See the full platform live with demo data — no camera or signup needed.
            </p>
            <button
              onClick={() => navigate('/login')}
              className="bg-slate-900 text-white font-bold px-8 py-4 rounded-xl text-lg hover:bg-slate-800 transition-colors"
            >
              🚀 Launch Demo Now
            </button>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="border-t border-surface-border/40 py-10 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-slate-500">
          <div className="flex items-center gap-2">
            <span className="text-xl">🛡️</span>
            <span className="font-bold text-slate-300">SafeGuard<span className="text-brand-500">AI</span></span>
          </div>
          <p>© 2026 SafeGuardAI · Industrial Safety Monitoring · Made in India 🇮🇳</p>
        </div>
      </footer>
    </div>
  )
}
