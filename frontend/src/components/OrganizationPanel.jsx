/**
 * OrganizationPanel.jsx
 *
 * Multi-tenant organization management.
 * Super-admin panel for creating, activating, suspending orgs.
 */
import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '../api/client'
import { useToast } from './Toast'

const PLAN_STYLES = {
  starter:    'text-gray-300 bg-gray-500/15 border-gray-500/30',
  growth:     'text-blue-300 bg-blue-500/15 border-blue-500/30',
  enterprise: 'text-purple-300 bg-purple-500/15 border-purple-500/30',
}

const STATUS_STYLES = {
  trial:           'text-yellow-300 bg-yellow-500/10',
  active:          'text-green-300 bg-green-500/10',
  suspended:       'text-red-300 bg-red-500/10',
  cancelled:       'text-gray-400 bg-gray-500/10',
  pending_payment: 'text-orange-300 bg-orange-500/10',
}

const INDUSTRY_ICONS = {
  construction: '🏗️', steel_manufacturing: '⚙️', oil_gas: '🛢️',
  pharma: '💊', warehouse: '📦', power_plant: '⚡',
  shipbuilding: '🚢', mining: '⛏️',
}

function CreateOrgModal({ onClose, onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({
    org_name: '', industry_type: 'construction', country: 'IN',
    plan: 'starter', admin_email: '',
  })
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (!form.org_name.trim()) return
    setLoading(true)
    try {
      const res = await apiClient.post('/organizations', form)
      onCreated?.(res.data)
      onClose?.()
      toast.success(`Organization "${form.org_name}" created`)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to create organization')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-96">
        <h3 className="text-white font-bold mb-4">Create Organization</h3>
        <div className="space-y-3">
          <input
            className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
            placeholder="Organization name *"
            value={form.org_name}
            onChange={e => setForm(f => ({ ...f, org_name: e.target.value }))}
            autoFocus
          />
          <div className="grid grid-cols-2 gap-2">
            <select
              value={form.industry_type}
              onChange={e => setForm(f => ({ ...f, industry_type: e.target.value }))}
              className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
            >
              {Object.keys(INDUSTRY_ICONS).map(i => (
                <option key={i} value={i}>
                  {INDUSTRY_ICONS[i]} {i.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
            <select
              value={form.plan}
              onChange={e => setForm(f => ({ ...f, plan: e.target.value }))}
              className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
            >
              <option value="starter">Starter ₹4,999/mo</option>
              <option value="growth">Growth ₹14,999/mo</option>
              <option value="enterprise">Enterprise ₹39,999/mo</option>
            </select>
          </div>
          <input
            className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
            placeholder="Admin email"
            value={form.admin_email}
            onChange={e => setForm(f => ({ ...f, admin_email: e.target.value }))}
          />
        </div>
        <div className="flex gap-2 mt-4">
          <button
            disabled={loading || !form.org_name.trim()}
            onClick={submit}
            className="flex-1 bg-brand-500 hover:bg-brand-600 disabled:opacity-40 text-slate-900 rounded-lg py-2 text-sm font-semibold"
          >
            {loading ? 'Creating…' : 'Create Organization'}
          </button>
          <button onClick={onClose} className="flex-1 bg-gray-700 hover:bg-gray-600 text-white rounded-lg py-2 text-sm">
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

function OrgCard({ org, onRefresh }) {
  const toast = useToast()
  const planStyle = PLAN_STYLES[org.plan] || PLAN_STYLES.starter
  const statusStyle = STATUS_STYLES[org.plan_status] || STATUS_STYLES.trial

  const handleAction = async (action) => {
    try {
      await apiClient.post(`/organizations/${org.org_id}/${action}`)
      onRefresh?.()
      toast.success(`Organization ${action === 'activate' ? 'activated' : 'suspended'}`)
    } catch (e) {
      toast.error(`Could not ${action} organization. Try again.`)
    }
  }

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 mb-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xl">{INDUSTRY_ICONS[org.industry_type] || '🏭'}</span>
            <span className="text-white font-bold text-sm truncate">{org.org_name}</span>
          </div>
          <div className="text-gray-400 text-xs mb-2">{org.org_id}</div>
          <div className="flex flex-wrap gap-1">
            <span className={`text-xs px-2 py-0.5 rounded-full border ${planStyle}`}>
              {org.plan}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${statusStyle}`}>
              {org.plan_status}
            </span>
            {org.admin_email && (
              <span className="text-xs text-gray-500">✉ {org.admin_email}</span>
            )}
          </div>
          <div className="text-gray-600 text-xs mt-1">
            📷 {org.max_cameras} cams • 🏢 {org.max_sites} sites • 👥 {org.max_users} users
          </div>
        </div>
        <div className="flex flex-col gap-1">
          {org.plan_status !== 'active' && (
            <button
              onClick={() => handleAction('activate')}
              className="bg-green-700 hover:bg-green-600 text-white text-xs px-3 py-1 rounded"
            >
              Activate
            </button>
          )}
          {org.plan_status === 'active' && (
            <button
              onClick={() => handleAction('suspend')}
              className="bg-red-800 hover:bg-red-700 text-white text-xs px-3 py-1 rounded"
            >
              Suspend
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function OrganizationPanel() {
  const [orgs, setOrgs] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState('')

  const fetchOrgs = useCallback(async () => {
    try {
      const res = await apiClient.get('/organizations?active_only=false')
      setOrgs(res.data.organizations || [])
    } catch (e) {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchOrgs() }, [fetchOrgs])

  const filtered = search
    ? orgs.filter(o =>
        o.org_name.toLowerCase().includes(search.toLowerCase()) ||
        o.org_id.toLowerCase().includes(search.toLowerCase())
      )
    : orgs

  const stats = {
    total: orgs.length,
    active: orgs.filter(o => o.plan_status === 'active').length,
    trial: orgs.filter(o => o.plan_status === 'trial').length,
    suspended: orgs.filter(o => o.plan_status === 'suspended').length,
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">🏢</span>
          <h2 className="text-white font-bold text-lg">Organizations</h2>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-brand-500 hover:bg-brand-600 text-slate-900 text-xs px-3 py-2 rounded-lg font-semibold"
        >
          + New Org
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {[
          { k: 'total',     label: 'Total',     color: 'gray' },
          { k: 'active',    label: 'Active',    color: 'green' },
          { k: 'trial',     label: 'Trial',     color: 'yellow' },
          { k: 'suspended', label: 'Suspended', color: 'red' },
        ].map(({ k, label, color }) => (
          <div key={k} className={`bg-${color}-500/10 border border-${color}-500/20 rounded-xl p-2 text-center`}>
            <div className={`text-${color}-400 font-bold text-xl`}>{stats[k]}</div>
            <div className="text-gray-500 text-xs">{label}</div>
          </div>
        ))}
      </div>

      {/* Search */}
      <input
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm mb-4"
        placeholder="Search organizations…"
        value={search}
        onChange={e => setSearch(e.target.value)}
      />

      <div className="flex-1 overflow-y-auto">
        {loading && <div className="text-gray-500 text-sm text-center py-8">Loading…</div>}
        {!loading && filtered.length === 0 && (
          <div className="text-gray-600 text-sm text-center py-8">
            No organizations found.<br />
            <button onClick={() => setShowCreate(true)} className="text-purple-400 underline mt-2">
              Create the first one
            </button>
          </div>
        )}
        {filtered.map(org => (
          <OrgCard key={org.org_id} org={org} onRefresh={fetchOrgs} />
        ))}
      </div>

      {showCreate && (
        <CreateOrgModal
          onClose={() => setShowCreate(false)}
          onCreated={fetchOrgs}
        />
      )}
    </div>
  )
}
