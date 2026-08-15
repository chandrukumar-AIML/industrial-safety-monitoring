import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const LEVEL_CONFIG = {
  CRITICAL: { color:"#dc2626", bg:"#7f1d1d", icon:"🚨" },
  WARNING : { color:"#ea580c", bg:"#7c2d12", icon:"⚠️" },
};

function ProximityAlertCard({ alert }) {
  const cfg = LEVEL_CONFIG[alert.alert_level] || LEVEL_CONFIG.WARNING;
  return (
    <div style={{
      background  : "#1e293b",
      border      : `1px solid ${cfg.color}`,
      borderRadius: 10,
      padding     : "12px 16px",
      marginBottom: 8,
      display     : "flex",
      alignItems  : "flex-start",
      gap         : 12,
    }}>
      <span style={{ fontSize:20, marginTop:2 }}>{cfg.icon}</span>
      <div style={{ flex:1 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:4 }}>
          <span style={{ color: cfg.color, fontWeight:700, fontSize:13 }}>
            {alert.alert_level} — Proximity Alert
          </span>
          <span style={{
            background  : cfg.bg,
            border      : `1px solid ${cfg.color}`,
            borderRadius: 12,
            color       : cfg.color,
            fontSize    : 10,
            padding     : "1px 8px",
            fontWeight  : 700,
          }}>
            {alert.machine_class?.toUpperCase()}
          </span>
        </div>
        <div style={{ color:"#94a3b8", fontSize:12, lineHeight:1.7 }}>
          <div>
            Worker <b style={{ color:"#f1f5f9" }}>#{alert.person_track_id}</b>
            {" → "}
            {alert.machine_class} <b style={{ color:"#f1f5f9" }}>
              #{alert.machine_track_id}
            </b>
          </div>
          <div>
            Distance:{" "}
            <b style={{ color: cfg.color }}>
              {alert.real_distance_m != null
                ? `${alert.real_distance_m.toFixed(1)}m`
                : `${alert.pixel_distance?.toFixed(0)}px`}
            </b>
          </div>
          {alert.zone_id && <div>Zone: {alert.zone_id}</div>}
          <div style={{ color:"#475569", fontSize:11, marginTop:2 }}>
            {alert.timestamp?.slice(11,19)} UTC
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ProximityPanel({ wsRef }) {
  const [alerts,   setAlerts]   = useState([]);
  const [liveAlerts,setLive]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [stats,    setStats]    = useState(null);

  const fetchAlerts = async () => {
    try {
      const res  = await fetch(`${API_BASE}/proximity-alerts?limit=30`);
      const data = await res.json();
      const arr = Array.isArray(data) ? data : [];
      setAlerts(arr);

      const cr = arr.filter((a) => a.alert_level === "CRITICAL").length;
      const wr = arr.filter((a) => a.alert_level === "WARNING").length;
      setStats({ critical: cr, warning: wr, total: arr.length });
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAlerts(); }, []);
  useEffect(() => {
    const t = setInterval(fetchAlerts, 10000);
    return () => clearInterval(t);
  }, []);

  // Live WebSocket proximity alerts
  useEffect(() => {
    if (!wsRef?.current) return;
    const handle = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type !== "proximity_alert") return;
        setLive((prev) => [
          { ...msg, id: Date.now(), timestamp: new Date().toISOString() },
          ...prev.slice(0, 4),
        ]);
        setTimeout(() => {
          setLive((prev) => prev.filter((a) => a.id !== msg.id));
        }, 10000);
        fetchAlerts();
      } catch {}
    };
    wsRef.current.addEventListener("message", handle);
    return () => wsRef.current?.removeEventListener("message", handle);
  }, [wsRef]);

  return (
    <div style={{ fontFamily:"system-ui", padding:"0 0 24px" }}>
      <h2 style={{ color:"#f1f5f9", fontSize:18, marginBottom:16 }}>
        Proximity Detection
      </h2>

      {/* Stats */}
      {stats && (
        <div style={{ display:"flex", gap:10, marginBottom:16, flexWrap:"wrap" }}>
          {[
            { label:"Total Events",  value:stats.total,    color:"#94a3b8" },
            { label:"Critical",      value:stats.critical,  color:"#dc2626" },
            { label:"Warning",       value:stats.warning,   color:"#ea580c" },
            { label:"Live Alerts",   value:liveAlerts.length, color:"#22c55e" },
          ].map(({ label, value, color }) => (
            <div
              key   = {label}
              style={{
                background  : "#1e293b",
                border      : "1px solid #334155",
                borderRadius: 10,
                padding     : "10px 16px",
                minWidth    : 110,
              }}
            >
              <div style={{ color, fontSize:11, marginBottom:2 }}>{label}</div>
              <div style={{ color:"#f1f5f9", fontSize:22, fontWeight:700 }}>
                {value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Calibration status */}
      <div style={{
        background  : "#1e293b",
        border      : "1px solid #334155",
        borderRadius: 8,
        padding     : "10px 14px",
        marginBottom: 16,
        fontSize    : 12,
        color       : "#64748b",
      }}>
        <b style={{ color:"#94a3b8" }}>Calibration:</b>{" "}
        Distances shown in metres when camera calibration is available.
        Run{" "}
        <code style={{
          background  : "#0f172a",
          padding     : "1px 6px",
          borderRadius: 4,
          color       : "#38bdf8",
        }}>
          python calibration/calibrate_camera.py --image frame.jpg
        </code>
        {" "}for accurate real-world distances.
      </div>

      {/* Live alerts */}
      {liveAlerts.length > 0 && (
        <>
          <h3 style={{ color:"#dc2626", fontSize:13, marginBottom:8 }}>
            🔴 Live Proximity Alerts
          </h3>
          {liveAlerts.map((a) => (
            <ProximityAlertCard key={a.id} alert={a} />
          ))}
        </>
      )}

      {/* Historical */}
      <h3 style={{ color:"#94a3b8", fontSize:13, margin:"16px 0 8px" }}>
        Recent Events
      </h3>
      {loading ? (
        <div style={{ color:"#64748b" }}>Loading...</div>
      ) : alerts.length === 0 ? (
        <div style={{ color:"#475569", fontSize:13 }}>
          No proximity alerts. Ensure machinery model is trained
          and MACHINERY_MODEL_PATH is set correctly.
        </div>
      ) : (
        alerts.map((a) => <ProximityAlertCard key={a.id} alert={a} />)
      )}
    </div>
  );
}