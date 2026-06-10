/**
 * ApiAccessPanel.jsx
 * Settings → API Access. Shows the organization's API key for programmatic
 * integrations (the key is for machine-to-machine use, NOT for human login —
 * humans sign in with email + password).
 */
import { useState } from 'react'
import { Copy, Check, Eye, EyeOff, KeyRound } from 'lucide-react'
import { useToast } from './Toast'

export default function ApiAccessPanel() {
  const toast = useToast()
  const [revealed, setRevealed] = useState(false)
  const [copied, setCopied] = useState(false)

  // The key the session authenticated with (set at login by AuthProvider).
  const apiKey = (() => {
    try { return sessionStorage.getItem('safety_monitor_api_key') || '' } catch { return '' }
  })()
  const orgId = (() => {
    try { return localStorage.getItem('active_org_id') || 'default' } catch { return 'default' }
  })()

  const masked = apiKey
    ? `${apiKey.slice(0, 6)}${'•'.repeat(20)}${apiKey.slice(-4)}`
    : 'No key on this session'

  const copy = async () => {
    if (!apiKey) return
    try {
      await navigator.clipboard.writeText(apiKey)
      setCopied(true)
      toast.success('API key copied to clipboard')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Could not copy. Select and copy manually.')
    }
  }

  return (
    <div className="bg-surface-raised border border-surface-border/60 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-1">
        <KeyRound size={16} className="text-brand-400" />
        <h3 className="text-sm font-semibold text-slate-200">API Access</h3>
      </div>
      <p className="text-slate-500 text-xs mb-4">
        Use this key to integrate SafeGuardAI with your own systems (cameras, ERP, HRMS).
        Keep it secret — it grants full API access for <span className="text-slate-400">{orgId}</span>.
      </p>

      <label className="block text-xs text-slate-500 mb-1.5">Organization API Key</label>
      <div className="flex items-center gap-2">
        <code className="flex-1 bg-surface border border-surface-border rounded-lg px-3 py-2.5 text-sm font-mono text-slate-300 truncate">
          {revealed ? (apiKey || masked) : masked}
        </code>
        <button
          onClick={() => setRevealed(r => !r)}
          className="p-2.5 rounded-lg border border-surface-border text-slate-400 hover:text-brand-400 hover:border-brand-500/40 transition-colors"
          aria-label={revealed ? 'Hide key' : 'Reveal key'}
          disabled={!apiKey}
        >
          {revealed ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
        <button
          onClick={copy}
          className="p-2.5 rounded-lg border border-surface-border text-slate-400 hover:text-brand-400 hover:border-brand-500/40 transition-colors"
          aria-label="Copy key"
          disabled={!apiKey}
        >
          {copied ? <Check size={15} className="text-emerald-400" /> : <Copy size={15} />}
        </button>
      </div>

      <div className="mt-4 bg-surface border border-surface-border/50 rounded-lg p-3">
        <p className="text-xs text-slate-500 mb-1.5">Example request</p>
        <code className="block text-xs font-mono text-slate-400 leading-relaxed whitespace-pre-wrap break-all">
          curl https://api.safeguardai.io/detections \{'\n'}
          {'  '}-H "Authorization: Bearer YOUR_API_KEY"
        </code>
      </div>

      <p className="text-slate-600 text-xs mt-3">
        Need a key for a new environment? Generate one from your plan in{' '}
        <span className="text-brand-400">Billing</span> after subscribing.
      </p>
    </div>
  )
}
