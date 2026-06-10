// src/components/LiveFeed.jsx
import { useEffect, useRef, useState } from 'react'
import PropTypes from 'prop-types'
import { VideoOff, AlertTriangle, Radio, Camera } from 'lucide-react'
import { useDemoMode } from '../hooks/useDemoMode'

export function LiveFeed({ frame = null, connected = false }) {
  const imgRef   = useRef(null)
  const isDemo   = useDemoMode()
  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    if (!frame?.jpeg_b64 || !imgRef.current) return
    setImgError(false)
    imgRef.current.src = `data:image/jpeg;base64,${frame.jpeg_b64}`
  }, [frame?.jpeg_b64])

  // Show the frame as soon as we have data — don't gate on `connected`
  // because that flag can lag behind the first frame by one render cycle.
  const showFeed = !!frame && !imgError

  return (
    <div className="bg-[#0d1117] border border-slate-800/60 rounded-xl
                    overflow-hidden flex flex-col h-full">

      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2.5
                      border-b border-slate-800/50">
        <div className="flex items-center gap-2">
          <Radio size={13} className="text-slate-500"/>
          <span className="text-xs font-medium text-slate-300">Live Feed</span>
        </div>
        {connected && (
          <span className="flex items-center gap-1.5 text-xs text-red-400">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse inline-block"/>
            REC
          </span>
        )}
      </div>

      {/* Video area */}
      <div className="relative bg-black aspect-video w-full"
           role="region" aria-label="Live camera feed">
        <img
          ref={imgRef}
          alt="Live annotated camera feed"
          className={`w-full h-full object-contain transition-opacity duration-150 ${
            showFeed ? 'opacity-100' : 'opacity-0'
          }`}
          onError={() => setImgError(true)}
        />

        {!showFeed && (
          <div className="absolute inset-0 flex flex-col items-center
                          justify-center text-slate-600 gap-3">
            {imgError ? (
              <>
                <AlertTriangle size={36} className="text-yellow-600/60"/>
                <span className="text-sm text-yellow-600/80">Frame decode error</span>
              </>
            ) : isDemo ? (
              <div className="flex flex-col items-center gap-3 px-6 text-center">
                <div className="flex items-center justify-center w-14 h-14 rounded-2xl
                                bg-brand-500/10 border border-brand-500/30">
                  <Camera size={26} className="text-brand-400"/>
                </div>
                <span className="text-sm font-medium text-slate-300">
                  No camera connected — demo mode
                </span>
                <span className="text-xs text-slate-500 max-w-xs">
                  Connect an RTSP/webcam stream to see live PPE detection here.
                  All other panels show synthetic demo data.
                </span>
              </div>
            ) : (
              <>
                <VideoOff size={36} className="text-slate-700"/>
                <span className="text-sm text-slate-600">
                  {connected ? 'Waiting for frames…' : 'Connecting to stream…'}
                </span>
              </>
            )}
          </div>
        )}

        {/* Overlay badges */}
        {frame && !imgError && (
          <div className="absolute top-2 left-2 flex gap-1.5 text-xs">
            <span className="bg-black/70 px-2 py-0.5 rounded-md
                             text-slate-300 font-mono">
              #{frame.frame_idx}
            </span>
            <span className="bg-black/70 px-2 py-0.5 rounded-md text-slate-300">
              {frame.active_tracks} track{frame.active_tracks !== 1 ? 's' : ''}
            </span>
            {frame.active_violations > 0 && (
              <span className="bg-red-900/80 border border-red-500/40 px-2 py-0.5
                               rounded-md text-red-300 font-medium animate-pulse"
                    role="alert" aria-live="assertive">
                ⚠ {frame.active_violations} violation{frame.active_violations !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

LiveFeed.propTypes = {
  frame    : PropTypes.object,
  connected: PropTypes.bool,
}

export default LiveFeed
