import { useState, useEffect, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STATUS_COLOR = {
  active  : "#22c55e",
  offline : "#dc2626",
  disabled: "#475569",
};

const LAYOUT_OPTIONS = [
  { label: "1×1", cols: 1, max: 1  },
  { label: "2×2", cols: 2, max: 4  },
  { label: "3×3", cols: 3, max: 9  },
  { label: "4×4", cols: 4, max: 16 },
];

// ── Single camera tile ────────────────────────────────────────
function CameraTile({ camera, wsFrames, selected, onSelect, tileSize }) {
  const canvasRef = useRef(null);

  // Draw WebSocket frame onto canvas
  useEffect(() => {
    const frameData = wsFrames[camera.camera_id];
    if (!frameData?.jpeg_b64) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const img = new Image();
    img.onload = () => ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    img.src    = `data:image/jpeg;base64,${frameData.jpeg_b64}`;
  }, [wsFrames, camera.camera_id]);

  const liveData     = wsFrames[camera.camera_id] || {};
  const violations   = liveData.violation_count ?? camera.violation_count ?? 0;
  const detections   = liveData.detection_count ?? camera.detection_count ?? 0;
  const fps          = liveData.fps             ?? camera.fps ?? 0;
  const isOnline     = camera.status === "active";

  return (
    <div
      onClick = {() => onSelect(camera.camera_id)}
      style   = {{
        position    : "relative",
        background  : "#000",
        borderRadius: 10,
        overflow    : "hidden",
        border      : selected
          ? "2px solid #2563eb"
          : `1px solid ${violations > 0 ? "#dc2626" : "#334155"}`,
        cursor      : "pointer",
        width       : tileSize,
        height      : tileSize * 0.5625,  // 16:9 aspect
      }}
    >
      {/* Video canvas */}
      {isOnline ? (
        <canvas
          ref    = {canvasRef}
          width  = {640}
          height = {360}
          style  = {{ width: "100%", height: "100%", display: "block" }}
        />
      ) : (
        <div style={{
          width          : "100%",
          height         : "100%",
          display        : "flex",
          alignItems     : "center",
          justifyContent : "center",
          flexDirection  : "column",
          gap            : 8,
          color          : "#475569",
          fontSize       : 14,
        }}>
          <span style={{ fontSize: 32 }}>📷</span>
          <span>Camera Offline</span>
          <span style={{ fontSize: 11 }}>{camera.camera_id}</span>
        </div>
      )}

      {/* Overlay HUD */}
      <div style={{
        position      : "absolute",
        bottom        : 0,
        left          : 0,
        right         : 0,
        background    : "linear-gradient(transparent, rgba(0,0,0,0.75))",
        padding       : "20px 8px 6px",
      }}>
        <div style={{
          display        : "flex",
          alignItems     : "center",
          justifyContent : "space-between",
        }}>
          <div>
            <div style={{ color: "#fff", fontWeight: 600, fontSize: 11 }}>
              {camera.camera_name}
            </div>
            <div style={{ color: "#94a3b8", fontSize: 10 }}>
              {camera.location}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 10, color: "#94a3b8" }}>
              {fps.toFixed(0)} FPS
            </div>
            <div style={{ fontSize: 10, color: "#94a3b8" }}>
              {detections} tracked
            </div>
          </div>
        </div>
      </div>

      {/* Status dot */}
      <div style={{
        position    : "absolute",
        top         : 6,
        left        : 6,
        width       : 7,
        height      : 7,
        borderRadius: "50%",
        background  : STATUS_COLOR[camera.status] || "#475569",
        boxShadow   : isOnline ? `0 0 6px ${STATUS_COLOR.active}` : "none",
      }} />

      {/* Violation badge */}
      {violations > 0 && (
        <div style={{
          position    : "absolute",
          top         : 4,
          right       : 4,
          background  : "#dc2626",
          color       : "#fff",
          borderRadius: 20,
          padding     : "2px 8px",
          fontSize    : 11,
          fontWeight  : 700,
          animation   : "pulse 1s infinite",
        }}>
          ⚠ {violations}
          <style>{`
            @keyframes pulse {
              0%,100% { opacity: 1; }
              50%      { opacity: 0.7; }
            }
          `}</style>
        </div>
      )}
    </div>
  );
}

// ── Add camera form ───────────────────────────────────────────
function AddCameraForm({ onAdd, onClose }) {
  const [form, setForm] = useState({
    camera_id  : "",
    camera_name: "",
    rtsp_url   : "",
    location   : "",
  });
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/cameras`, {
        method  : "POST",
        headers : { "Content-Type": "application/json" },
        body    : JSON.stringify(form),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to add camera");
      }
      await onAdd();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    width       : "100%",
    background  : "#0f172a",
    border      : "1px solid #334155",
    borderRadius: 8,
    color       : "#f1f5f9",
    padding     : "8px 12px",
    fontSize    : 13,
    boxSizing   : "border-box",
  };

  return (
    <div style={{
      position      : "fixed",
      inset         : 0,
      background    : "rgba(0,0,0,0.6)",
      display       : "flex",
      alignItems    : "center",
      justifyContent: "center",
      zIndex        : 1000,
    }}>
      <div style={{
        background  : "#1e293b",
        borderRadius: 14,
        padding     : 24,
        width       : 420,
        border      : "1px solid #334155",
      }}>
        <h3 style={{ color: "#f1f5f9", margin: "0 0 16px", fontSize: 16 }}>
          Add Camera
        </h3>

        {error && (
          <div style={{
            background  : "#7f1d1d",
            borderRadius: 8,
            padding     : "8px 12px",
            color       : "#fca5a5",
            fontSize    : 12,
            marginBottom: 12,
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {[
            { label: "Camera ID",   key: "camera_id",   placeholder: "cam-entrance" },
            { label: "Camera Name", key: "camera_name",  placeholder: "Site Entrance" },
            { label: "RTSP URL",    key: "rtsp_url",     placeholder: "rtsp://user:pass@192.168.1.100/stream" },
            { label: "Location",    key: "location",     placeholder: "North gate" },
          ].map(({ label, key, placeholder }) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <label style={{ color: "#94a3b8", fontSize: 11, display: "block", marginBottom: 4 }}>
                {label}
              </label>
              <input
                required
                value       = {form[key]}
                onChange    = {(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                placeholder = {placeholder}
                style       = {inputStyle}
              />
            </div>
          ))}

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button
              type  = "submit"
              disabled = {saving}
              style = {{
                flex        : 1,
                background  : "#2563eb",
                border      : "none",
                borderRadius: 8,
                color       : "#fff",
                padding     : "9px",
                cursor      : saving ? "wait" : "pointer",
                fontWeight  : 600,
                fontSize    : 13,
              }}
            >
              {saving ? "Adding..." : "Add Camera"}
            </button>
            <button
              type    = "button"
              onClick = {onClose}
              style   = {{
                background  : "#334155",
                border      : "none",
                borderRadius: 8,
                color       : "#f1f5f9",
                padding     : "9px 16px",
                cursor      : "pointer",
                fontSize    : 13,
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main CameraGrid component ─────────────────────────────────
export default function CameraGrid({ wsRef }) {
  const [cameras,   setCameras]   = useState([]);
  const [layout,    setLayout]    = useState(LAYOUT_OPTIONS[1]);  // 2×2 default
  const [selected,  setSelected]  = useState(null);
  const [wsFrames,  setWsFrames]  = useState({});
  const [showAdd,   setShowAdd]   = useState(false);
  const [loading,   setLoading]   = useState(true);

  // Fetch camera list from REST
  const fetchCameras = async () => {
    try {
      const res  = await fetch(`${API_BASE}/cameras/grid`);
      const data = await res.json();
      setCameras(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCameras(); }, []);
  useEffect(() => {
    const t = setInterval(fetchCameras, 10000);
    return () => clearInterval(t);
  }, []);

  // WebSocket live frame updates
  useEffect(() => {
    if (!wsRef?.current) return;
    const handle = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type !== "camera_frame") return;
        setWsFrames((prev) => ({
          ...prev,
          [msg.camera_id]: {
            jpeg_b64       : msg.jpeg_b64,
            violation_count: msg.violation_count,
            detection_count: msg.detection_count,
            fps            : msg.fps,
            timestamp      : msg.timestamp,
          },
        }));
      } catch {}
    };
    wsRef.current.addEventListener("message", handle);
    return () => wsRef.current?.removeEventListener("message", handle);
  }, [wsRef]);

  const totalViolations = cameras.reduce((s, c) => {
    const live = wsFrames[c.camera_id];
    return s + (live?.violation_count ?? c.violation_count ?? 0);
  }, 0);
  const onlineCount = cameras.filter((c) => c.status === "active").length;

  const containerWidth = 900;   // approximate grid container width
  const gap            = 10;
  const cols           = layout.cols;
  const tileWidth      = (containerWidth - gap * (cols - 1)) / cols;

  return (
    <div style={{ fontFamily: "system-ui", padding: "0 0 24px" }}>
      {/* Header controls */}
      <div style={{
        display       : "flex",
        alignItems    : "center",
        gap           : 12,
        marginBottom  : 16,
        flexWrap      : "wrap",
      }}>
        <h2 style={{ color: "#f1f5f9", fontSize: 18, margin: 0 }}>
          Camera Grid
        </h2>

        {/* Status pills */}
        <div style={{ display: "flex", gap: 8 }}>
          <span style={{
            background  : "#14532d",
            color       : "#86efac",
            borderRadius: 20,
            padding     : "2px 10px",
            fontSize    : 11,
            fontWeight  : 600,
          }}>
            {onlineCount} online
          </span>
          {totalViolations > 0 && (
            <span style={{
              background  : "#7f1d1d",
              color       : "#fca5a5",
              borderRadius: 20,
              padding     : "2px 10px",
              fontSize    : 11,
              fontWeight  : 700,
            }}>
              ⚠ {totalViolations} violations
            </span>
          )}
        </div>

        {/* Layout selector */}
        <div style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
          {LAYOUT_OPTIONS.map((opt) => (
            <button
              key     = {opt.label}
              onClick = {() => setLayout(opt)}
              style   = {{
                background  : layout.label === opt.label ? "#2563eb" : "#1e293b",
                border      : "1px solid #334155",
                borderRadius: 6,
                color       : "#f1f5f9",
                padding     : "4px 10px",
                cursor      : "pointer",
                fontSize    : 12,
                fontWeight  : layout.label === opt.label ? 700 : 400,
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <button
          onClick = {() => setShowAdd(true)}
          style   = {{
            background  : "#2563eb",
            border      : "none",
            borderRadius: 8,
            color       : "#fff",
            padding     : "6px 14px",
            cursor      : "pointer",
            fontWeight  : 600,
            fontSize    : 13,
          }}
        >
          + Add Camera
        </button>
      </div>

      {/* Camera grid */}
      {loading ? (
        <div style={{ color: "#64748b", padding: 40, textAlign: "center" }}>
          Loading cameras...
        </div>
      ) : cameras.length === 0 ? (
        <div style={{
          background  : "#1e293b",
          borderRadius: 12,
          padding     : 40,
          textAlign   : "center",
          color       : "#475569",
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📷</div>
          <div style={{ fontSize: 14, marginBottom: 8 }}>No cameras configured</div>
          <div style={{ fontSize: 12, color: "#334155" }}>
            Click "Add Camera" to connect your first RTSP stream
          </div>
        </div>
      ) : (
        <div style={{
          display            : "grid",
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap                : gap,
        }}>
          {cameras.slice(0, layout.max).map((cam) => (
            <CameraTile
              key       = {cam.camera_id}
              camera    = {cam}
              wsFrames  = {wsFrames}
              selected  = {selected === cam.camera_id}
              onSelect  = {setSelected}
              tileWidth = {tileWidth}
            />
          ))}
          {/* Empty slots */}
          {Array.from({
            length: Math.max(0, layout.max - cameras.length)
          }).map((_, i) => (
            <div
              key   = {`empty-${i}`}
              style = {{
                background  : "#0f172a",
                borderRadius: 10,
                border      : "1px dashed #1e293b",
                display     : "flex",
                alignItems  : "center",
                justifyContent: "center",
                aspectRatio : "16/9",
                color       : "#334155",
                fontSize    : 12,
                cursor      : "pointer",
              }}
              onClick={() => setShowAdd(true)}
            >
              + Add Camera
            </div>
          ))}
        </div>
      )}

      {/* Add camera modal */}
      {showAdd && (
        <AddCameraForm
          onAdd  = {fetchCameras}
          onClose= {() => setShowAdd(false)}
        />
      )}
    </div>
  );
}