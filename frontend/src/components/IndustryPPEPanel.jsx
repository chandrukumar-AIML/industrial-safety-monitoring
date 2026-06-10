/**
 * IndustryPPEPanel.jsx
 *
 * Industry-specific PPE profile browser.
 * Shows required PPE per industry per zone type.
 * Includes compliance check tool.
 */
import { useState, useEffect } from 'react'
import { apiClient } from '../api/client'
import { useToast } from './Toast'

const INDUSTRY_ICONS = {
  construction:       '🏗️',
  steel_manufacturing:'⚙️',
  oil_gas:            '🛢️',
  pharma:             '💊',
  warehouse:          '📦',
  power_plant:        '⚡',
  shipbuilding:       '🚢',
  mining:             '⛏️',
  textile:            '🧵',
}

const RISK_STYLES = {
  LOW:      'bg-green-500/15 text-green-300 border-green-500/30',
  MEDIUM:   'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  HIGH:     'bg-orange-500/15 text-orange-300 border-orange-500/30',
  CRITICAL: 'bg-red-500/15 text-red-300 border-red-500/30',
}

const PPE_ICONS = {
  'no hardhat':  '⛑️',
  'no vest':     '🦺',
  'no gloves':   '🧤',
  'no boots':    '👢',
  'no goggles':  '🥽',
  'no mask':     '😷',
  'no suit':     '👔',
  'no harness':  '🪢',
}

function ComplianceChecker() {
  const [industry, setIndustry] = useState('construction')
  const [zone, setZone] = useState('general')
  const [ppe, setPpe] = useState('no hardhat')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const check = async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/industry-ppe/check', {
        params: { industry_type: industry, zone_type: zone, detected_class: ppe },
      })
      setResult(res.data)
    } catch (e) {
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 mb-4">
      <h3 className="text-white font-medium text-sm mb-3">🔍 Compliance Check</h3>
      <div className="grid grid-cols-3 gap-2 mb-2">
        <input
          className="bg-gray-700 border border-gray-600 rounded-lg px-2 py-2 text-white text-xs"
          placeholder="Industry"
          value={industry}
          onChange={e => setIndustry(e.target.value)}
        />
        <input
          className="bg-gray-700 border border-gray-600 rounded-lg px-2 py-2 text-white text-xs"
          placeholder="Zone type"
          value={zone}
          onChange={e => setZone(e.target.value)}
        />
        <input
          className="bg-gray-700 border border-gray-600 rounded-lg px-2 py-2 text-white text-xs"
          placeholder="PPE class"
          value={ppe}
          onChange={e => setPpe(e.target.value)}
        />
      </div>
      <button
        onClick={check}
        disabled={loading}
        className="w-full bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-slate-900 font-semibold rounded-lg py-2 text-sm"
      >
        Check
      </button>
      {result && (
        <div className={`mt-3 p-3 rounded-lg border ${result.is_violation ? 'bg-red-500/15 border-red-500/40' : 'bg-green-500/15 border-green-500/40'}`}>
          <div className="flex items-center gap-2">
            <span className="text-2xl">{result.is_violation ? '🚨' : '✅'}</span>
            <div>
              <div className={`font-bold ${result.is_violation ? 'text-red-300' : 'text-green-300'}`}>
                {result.is_violation ? 'VIOLATION — PPE Required' : 'Not Required Here'}
              </div>
              <div className="text-gray-400 text-xs">{result.compliance_standard}</div>
            </div>
          </div>
          {result.required_ppe?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {result.required_ppe.map(p => (
                <span key={p} className="bg-gray-700 text-gray-300 text-xs px-2 py-0.5 rounded-full">
                  {PPE_ICONS[p] || '🦺'} {p}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function IndustryPPEPanel() {
  const toast = useToast()
  const [byIndustry, setByIndustry] = useState({})
  const [industries, setIndustries] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [seeding, setSeeding] = useState(false)

  const fetchProfiles = async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/industry-ppe/profiles')
      setByIndustry(res.data.by_industry || {})
      setIndustries(res.data.industries || [])
      if (!selected && res.data.industries?.length > 0) {
        setSelected(res.data.industries[0])
      }
    } catch (e) {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  const seedProfiles = async () => {
    setSeeding(true)
    try {
      const res = await apiClient.post('/industry-ppe/seed')
      await fetchProfiles()
      toast.success(`Seeded ${res.data.inserted} profiles (${res.data.skipped} already existed)`)
    } catch (e) {
      toast.error('Could not seed profiles. Try again.')
    } finally {
      setSeeding(false)
    }
  }

  useEffect(() => { fetchProfiles() }, [])

  const profiles = selected ? (byIndustry[selected] || []) : []

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">🏭</span>
          <h2 className="text-white font-bold text-lg">Industry PPE Profiles</h2>
        </div>
        <button
          onClick={seedProfiles}
          disabled={seeding}
          className="bg-brand-500/15 border border-brand-500/40 hover:bg-brand-500/25 disabled:opacity-50 text-brand-300 text-xs px-3 py-1.5 rounded-lg"
        >
          {seeding ? '…' : '🌱 Seed Defaults'}
        </button>
      </div>

      <ComplianceChecker />

      {/* Industry tabs */}
      <div className="flex flex-wrap gap-1 mb-4">
        {industries.map(ind => (
          <button
            key={ind}
            onClick={() => setSelected(ind)}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              selected === ind
                ? 'bg-orange-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            {INDUSTRY_ICONS[ind] || '🏭'} {ind.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Profile list */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {loading && <div className="text-gray-500 text-sm text-center py-4">Loading…</div>}
        {!loading && industries.length === 0 && (
          <div className="text-gray-500 text-sm text-center py-8">
            No profiles loaded.<br />
            <button onClick={seedProfiles} className="text-orange-400 underline mt-2">
              Click Seed Defaults to load 23 industry profiles
            </button>
          </div>
        )}
        {profiles.map(p => {
          const riskStyle = RISK_STYLES[p.risk_level] || RISK_STYLES.MEDIUM
          return (
            <div key={p.id} className={`border rounded-xl p-3 ${riskStyle}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-white font-medium text-sm capitalize">
                  {p.zone_type.replace(/_/g, ' ')} Zone
                </span>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${riskStyle}`}>
                  {p.risk_level}
                </span>
              </div>
              <div className="flex flex-wrap gap-1 mb-2">
                {(p.required_ppe || []).map(ppe => (
                  <span key={ppe} className="bg-gray-800/60 text-gray-300 text-xs px-2 py-0.5 rounded-full">
                    {PPE_ICONS[ppe] || '🦺'} {ppe}
                  </span>
                ))}
              </div>
              <div className="text-xs text-gray-500">{p.compliance_standard}</div>
              {p.notes && <div className="text-xs text-gray-600 mt-0.5 italic">{p.notes}</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
