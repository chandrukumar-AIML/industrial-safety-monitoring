// src/components/SHAPModal.jsx
import { useQuery }        from '@tanstack/react-query'
import { getSHAP }         from '../api/client'
import { X, Loader2, AlertTriangle, Sparkles } from 'lucide-react'
import { useEffect, useRef } from 'react'
import PropTypes from 'prop-types'

export function SHAPModal({ violation, onClose }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey : ['shap', violation.track_id],
    queryFn  : () => getSHAP(violation.track_id).then(r => r.data),
    staleTime: 30_000,
    retry    : 0,
  })

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const containerRef = useRef(null)
  useEffect(() => { containerRef.current?.focus() }, [])

  const errorMsg = (() => {
    const status = error?.response?.status
    if (status === 404) return 'Track is no longer active in the current frame.'
    if (status === 503) return 'SHAP explainer is not initialised on the server.'
    if (status === 429) return 'Rate limit exceeded. Try again in a moment.'
    return 'SHAP computation failed. Please try again.'
  })()

  return (
    <div
      className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center
                 justify-center z-50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={containerRef}
        tabIndex={-1}
        className="bg-[#111520] border border-slate-700/50 rounded-2xl
                   w-full max-w-lg p-5 relative outline-none shadow-2xl"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`SHAP explanation for track ${violation.track_id}`}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-500 hover:text-slate-200
                     transition-colors"
          aria-label="Close explanation"
        >
          <X size={15}/>
        </button>

        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={14} className="text-purple-400"/>
          <h3 className="font-semibold text-slate-100 text-sm">SHAP Explanation</h3>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Track <span className="font-mono text-slate-400">#{violation.track_id}</span>
          &nbsp;·&nbsp;
          <span className="text-orange-400/80">{violation.class_name}</span>
          &nbsp;·&nbsp;
          {(violation.confidence * 100).toFixed(0)}% confidence
        </p>

        {isLoading && (
          <div className="flex items-center justify-center h-48 gap-2
                          text-slate-500 text-sm">
            <Loader2 size={16} className="animate-spin text-purple-400"/>
            Computing saliency map…
          </div>
        )}

        {isError && (
          <div className="flex flex-col items-center justify-center
                          h-48 gap-3 text-red-400">
            <AlertTriangle size={24}/>
            <p className="text-sm text-center text-red-400/80">{errorMsg}</p>
          </div>
        )}

        {data && (
          <>
            <img
              src={`data:image/png;base64,${data.saliency_b64}`}
              alt={`SHAP saliency map for ${violation.class_name} detection`}
              className="w-full rounded-xl mb-4 border border-slate-700/30"
            />
            <div>
              <p className="text-xs text-slate-500 mb-2 font-medium uppercase tracking-wider">
                Top contributing regions
              </p>
              <div className="flex flex-wrap gap-1.5">
                {data.top_regions.map((r, i) => (
                  <span key={i}
                        className="bg-slate-800 border border-slate-700/50
                                   text-slate-300 px-2 py-0.5 rounded-md text-xs">
                    {r.zone}
                    <span className="text-slate-500 ml-1 font-mono">
                      {r.shap_value?.toFixed(3)}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

SHAPModal.propTypes = {
  violation: PropTypes.shape({
    track_id  : PropTypes.number.isRequired,
    class_name: PropTypes.string.isRequired,
    confidence: PropTypes.number.isRequired,
  }).isRequired,
  onClose: PropTypes.func.isRequired,
}

export default SHAPModal
