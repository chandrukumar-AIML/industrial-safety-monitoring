/**
 * BillingPanel.jsx
 *
 * Subscription billing management — plan selection, upgrade, cancel.
 * Razorpay integration (India-first). Shows plan features and pricing.
 */
import { useState, useEffect } from 'react'
import { apiClient } from '../api/client'
import { useToast } from './Toast'

const PLAN_COLORS = {
  starter:    { from: 'from-gray-700', to: 'to-gray-600', accent: 'gray', badge: '🥉' },
  growth:     { from: 'from-blue-800', to: 'to-blue-700', accent: 'blue', badge: '🥈' },
  enterprise: { from: 'from-purple-800', to: 'to-purple-700', accent: 'purple', badge: '🥇' },
}

function PlanCard({ plan, current, orgId, onSubscribed }) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [cycle, setCycle] = useState('monthly')
  const colors = PLAN_COLORS[plan.plan_id] || PLAN_COLORS.starter
  const isCurrentPlan = current?.plan === plan.plan_id

  const subscribe = async () => {
    if (!orgId) { toast.warning('Enter an Organization ID first'); return }
    setLoading(true)
    try {
      const res = await apiClient.post('/billing/subscribe', {
        org_id: orgId,
        plan: plan.plan_id,
        billing_cycle: cycle,
      })
      if (res.data.payment_link) {
        window.open(res.data.payment_link, '_blank')
      } else {
        toast.success(`${plan.name} plan activated!`)
      }
      onSubscribed?.()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Subscription failed')
    } finally {
      setLoading(false)
    }
  }

  const price = cycle === 'annual' ? plan.pricing.annual_inr : plan.pricing.monthly_inr
  const savings = plan.pricing.annual_savings_pct

  return (
    <div className={`bg-gradient-to-b ${colors.from} ${colors.to} border border-${colors.accent}-600/40 rounded-2xl p-5 flex flex-col`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-2xl">{colors.badge}</span>
        <span className="text-white font-bold text-xl">{plan.name}</span>
        {isCurrentPlan && (
          <span className="bg-green-600 text-white text-xs px-2 py-0.5 rounded-full ml-auto">Current</span>
        )}
      </div>

      {/* Billing toggle */}
      <div className="flex gap-1 mb-3 bg-black/20 rounded-lg p-1">
        {['monthly', 'annual'].map(c => (
          <button
            key={c}
            onClick={() => setCycle(c)}
            className={`flex-1 py-1 rounded text-xs font-medium transition-colors ${
              cycle === c ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            {c} {c === 'annual' && savings > 0 && (
              <span className="text-green-400">-{savings}%</span>
            )}
          </button>
        ))}
      </div>

      {/* Price */}
      <div className="mb-3">
        <span className="text-white text-3xl font-bold">₹{price.toLocaleString()}</span>
        <span className="text-gray-400 text-sm">/{cycle === 'annual' ? 'year' : 'month'}</span>
      </div>

      {/* Limits */}
      <div className="grid grid-cols-3 gap-1 mb-3 text-center">
        <div className="bg-black/20 rounded-lg p-1.5">
          <div className="text-white font-bold text-sm">
            {plan.limits.max_cameras === 9999 ? '∞' : plan.limits.max_cameras}
          </div>
          <div className="text-gray-400 text-xs">cams</div>
        </div>
        <div className="bg-black/20 rounded-lg p-1.5">
          <div className="text-white font-bold text-sm">
            {plan.limits.max_sites === 9999 ? '∞' : plan.limits.max_sites}
          </div>
          <div className="text-gray-400 text-xs">sites</div>
        </div>
        <div className="bg-black/20 rounded-lg p-1.5">
          <div className="text-white font-bold text-sm">
            {plan.limits.max_users === 9999 ? '∞' : plan.limits.max_users}
          </div>
          <div className="text-gray-400 text-xs">users</div>
        </div>
      </div>

      {/* Features */}
      <ul className="flex-1 space-y-1 mb-4">
        {plan.features.slice(0, 6).map((f, i) => (
          <li key={i} className="text-gray-300 text-xs flex items-start gap-1.5">
            <span className="text-green-400 mt-0.5">✓</span> {f}
          </li>
        ))}
        {plan.features.length > 6 && (
          <li className="text-gray-500 text-xs">+{plan.features.length - 6} more features</li>
        )}
      </ul>

      <button
        onClick={subscribe}
        disabled={loading || isCurrentPlan}
        className={`w-full py-2.5 rounded-xl text-sm font-bold transition-colors disabled:opacity-50 ${
          isCurrentPlan
            ? 'bg-green-800 text-green-300 cursor-default'
            : `bg-${colors.accent}-600 hover:bg-${colors.accent}-700 text-white`
        }`}
      >
        {loading ? 'Processing…' : isCurrentPlan ? '✓ Current Plan' : `Subscribe — ₹${price.toLocaleString()}`}
      </button>
    </div>
  )
}

export default function BillingPanel() {
  const toast = useToast()
  const [plans, setPlans] = useState([])
  const [subscription, setSubscription] = useState(null)
  const [orgId, setOrgId] = useState(localStorage.getItem('active_org_id') || '')
  const [loading, setLoading] = useState(true)
  const [cancelling, setCancelling] = useState(false)

  const fetchData = async () => {
    try {
      const plansRes = await apiClient.get('/billing/plans')
      setPlans(plansRes.data.plans || [])

      if (orgId) {
        const subRes = await apiClient.get(`/billing/subscription/${orgId}`)
        setSubscription(subRes.data)
      }
    } catch (e) {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [orgId])

  const handleOrgIdSave = (id) => {
    setOrgId(id)
    localStorage.setItem('active_org_id', id)
  }

  const handleCancel = async () => {
    if (!orgId || !confirm('Cancel subscription?')) return
    setCancelling(true)
    try {
      await apiClient.post(`/billing/cancel/${orgId}`)
      fetchData()
      toast.success('Subscription cancelled')
    } catch (e) {
      toast.error('Could not cancel subscription. Try again.')
    } finally {
      setCancelling(false)
    }
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 p-4 h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xl">💳</span>
        <h2 className="text-white font-bold text-lg">Billing & Plans</h2>
        <span className="text-gray-500 text-xs ml-auto">India (INR) • Razorpay</span>
      </div>

      {/* Org ID input */}
      <div className="flex gap-2 mb-4">
        <input
          className="flex-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
          placeholder="Organization ID"
          defaultValue={orgId}
          onBlur={e => handleOrgIdSave(e.target.value.trim())}
        />
        {subscription && (
          <div className={`flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-medium ${
            subscription.plan_status === 'active' ? 'bg-green-900/40 text-green-300' : 'bg-yellow-900/40 text-yellow-300'
          }`}>
            {subscription.plan_status}
          </div>
        )}
      </div>

      {/* Current sub summary */}
      {subscription?.subscription && (
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-3 mb-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-white font-medium capitalize">{subscription.subscription.plan} Plan</div>
              <div className="text-gray-400 text-xs">
                ₹{(subscription.subscription.amount_paise / 100).toLocaleString()}/{subscription.subscription.billing_cycle}
                {' • '}
                {subscription.subscription.status}
              </div>
            </div>
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="text-red-400 hover:text-red-300 text-xs underline disabled:opacity-50"
            >
              {cancelling ? 'Cancelling…' : 'Cancel'}
            </button>
          </div>
        </div>
      )}

      {/* Plan cards */}
      <div className="flex-1 overflow-y-auto">
        {loading && <div className="text-gray-500 text-center py-8">Loading plans…</div>}
        <div className="grid grid-cols-1 gap-4">
          {plans.map(plan => (
            <PlanCard
              key={plan.plan_id}
              plan={plan}
              current={subscription}
              orgId={orgId}
              onSubscribed={fetchData}
            />
          ))}
        </div>

        {/* Razorpay note */}
        <div className="mt-4 text-center text-gray-600 text-xs">
          Secure payments via Razorpay • UPI, Cards, Net Banking, EMI
        </div>
      </div>
    </div>
  )
}
