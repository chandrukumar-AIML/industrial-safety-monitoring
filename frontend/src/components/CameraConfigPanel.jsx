/**
 * frontend/src/components/CameraConfigPanel.jsx
 *
 * Camera RTSP/USB configuration UI.
 * Lets operators add, test, and manage camera sources without touching the API directly.
 *
 * Integrates with:
 *   GET  /cameras        — list cameras
 *   POST /cameras        — register new camera
 *   PUT  /cameras/{id}   — update camera
 *   DELETE /cameras/{id} — remove camera
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SOURCE_PRESETS = [
  { label: 'USB Webcam (cam 0)', value: '0' },
  { label: 'USB Webcam (cam 1)', value: '1' },
  { label: 'RTSP Stream', value: 'rtsp://' },
  { label: 'HTTP Stream', value: 'http://' },
  { label: 'Video File', value: '/app/data/video.mp4' },
]

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return null
  return res.json()
}

const defaultForm = {
  camera_id: '',
  name: '',
  source_url: '0',
  location: '',
  active: true,
}

const STATUS_COLORS = {
  active: 'text-emerald-400 bg-emerald-900/30',
  disabled: 'text-slate-400 bg-slate-800/40',
  error: 'text-red-400 bg-red-900/30',
  connecting: 'text-amber-400 bg-amber-900/30',
}

export default function CameraConfigPanel() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(defaultForm)
  const [formError, setFormError] = useState('')
  const [customSource, setCustomSource] = useState(false)

  const { data: cameras = [], isLoading } = useQuery({
    queryKey: ['cameras-config'],
    queryFn: () => apiFetch('/cameras'),
    refetchInterval: 15_000,
  })

  const createMut = useMutation({
    mutationFn: (body) => apiFetch('/cameras', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras-config'] })
      setShowForm(false)
      setForm(defaultForm)
      setFormError('')
    },
    onError: (err) => setFormError(err.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id) => apiFetch(`/cameras/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cameras-config'] }),
  })

  function handleSourcePreset(e) {
    const val = e.target.value
    if (val === '__custom__') {
      setCustomSource(true)
      setForm(f => ({ ...f, source_url: '' }))
    } else {
      setCustomSource(false)
      setForm(f => ({ ...f, source_url: val }))
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (!form.camera_id.trim()) { setFormError('Camera ID is required'); return }
    if (!form.name.trim()) { setFormError('Name is required'); return }
    if (!form.source_url.trim()) { setFormError('Source URL is required'); return }
    setFormError('')
    createMut.mutate({
      camera_id: form.camera_id.toLowerCase().replace(/\s+/g, '-'),
      name: form.name,
      source_url: form.source_url,
      location: form.location || undefined,
      active: form.active,
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">📷 Camera Configuration</h2>
          <p className="text-xs text-slate-500 mt-0.5">Manage RTSP streams, USB cameras, and video sources</p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          className="px-3 py-1.5 bg-brand-500 hover:bg-brand-600 text-slate-900 font-semibold text-sm rounded-md transition-colors"
        >
          {showForm ? '✕ Cancel' : '+ Add Camera'}
        </button>
      </div>

      {/* Add camera form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="bg-slate-800/60 rounded-lg p-4 space-y-3 border border-slate-700/50">
          <h3 className="text-sm font-semibold text-slate-300">Register New Camera</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Camera ID * <span className="text-slate-600">(slug, no spaces)</span></label>
              <input
                className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
                placeholder="cam-entrance-01"
                value={form.camera_id}
                onChange={e => setForm(f => ({ ...f, camera_id: e.target.value }))}
                required
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Display Name *</label>
              <input
                className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
                placeholder="Entrance Gate Camera"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                required
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Video Source *</label>
            <select
              className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500 mb-2"
              onChange={handleSourcePreset}
              defaultValue=""
            >
              <option value="" disabled>— Select source type —</option>
              {SOURCE_PRESETS.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
              <option value="__custom__">Custom URL / path…</option>
            </select>
            {(customSource || form.source_url.startsWith('rtsp') || form.source_url.startsWith('http')) && (
              <input
                className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
                placeholder="rtsp://admin:pass@192.168.1.100:554/stream1"
                value={form.source_url}
                onChange={e => setForm(f => ({ ...f, source_url: e.target.value }))}
              />
            )}
            {!customSource && !form.source_url.startsWith('rtsp') && !form.source_url.startsWith('http') && form.source_url && (
              <p className="text-xs text-slate-500 mt-1">Source: <code className="text-slate-400">{form.source_url}</code></p>
            )}
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Location <span className="text-slate-600">(optional)</span></label>
            <input
              className="w-full bg-slate-900/60 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
              placeholder="Factory Floor B, Section 3"
              value={form.location}
              onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="cam-active"
              checked={form.active}
              onChange={e => setForm(f => ({ ...f, active: e.target.checked }))}
              className="accent-blue-500"
            />
            <label htmlFor="cam-active" className="text-xs text-slate-300">Enable camera immediately</label>
          </div>

          {formError && <p className="text-xs text-red-400">{formError}</p>}

          <button
            type="submit"
            disabled={createMut.isPending}
            className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm rounded-md transition-colors"
          >
            {createMut.isPending ? 'Adding…' : 'Add Camera'}
          </button>
        </form>
      )}

      {/* Camera list */}
      {isLoading ? (
        <div className="text-slate-400 text-sm">Loading cameras…</div>
      ) : cameras.length === 0 ? (
        <div className="text-slate-500 text-sm text-center py-8 border border-dashed border-slate-700 rounded-lg">
          No cameras configured yet. Add a camera to start monitoring.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {cameras.map(cam => {
            const statusCls = STATUS_COLORS[cam.status] || STATUS_COLORS.disabled
            return (
              <div key={cam.camera_id || cam.id} className="bg-slate-800/60 rounded-lg p-4 border border-slate-700/50">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm text-slate-200">{cam.name || cam.camera_id}</span>
                      {cam.status && (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${statusCls}`}>
                          {cam.status}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 mt-1 font-mono truncate">
                      {cam.source_url || cam.rtsp_url || cam.camera_id}
                    </p>
                    {cam.location && (
                      <p className="text-xs text-slate-600 mt-0.5">📍 {cam.location}</p>
                    )}
                    {cam.fps != null && (
                      <p className="text-xs text-slate-500 mt-1">
                        FPS: {cam.fps} · Frames: {cam.total_frames?.toLocaleString() || '—'}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => deleteMut.mutate(cam.camera_id || cam.id)}
                    disabled={deleteMut.isPending}
                    className="px-2 py-1 bg-red-900/30 hover:bg-red-800/40 text-red-400 text-xs rounded transition-colors disabled:opacity-50 flex-shrink-0"
                    title="Remove camera"
                  >
                    🗑️
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
