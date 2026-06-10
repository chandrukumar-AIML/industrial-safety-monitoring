import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const HAZARD_CONFIG = {
  dangerous_bending      : { icon:"🔄", label:"Dangerous Bending",     color:"#ea580c" },
  reaching_restricted_area:{ icon:"✋", label:"Reaching into Restricted",color:"#dc2626" },
  fatigue_posture        : { icon:"😴", label:"Fatigue Posture",        color:"#ca8a04" },
  fall_detected          : { icon:"⚠",  label:"Fall Detected",          color:"#7c3aed" },
};

const SEVERITY_COLOR = {
  CRITICAL: "#dc2626",
  HIGH    : "#ea580c",
  MEDIUM  : "#ca8a04",
  LOW     : "#16a34a",
};

function HazardCard({ event }) {
  const cfg = HAZARD_CONFIG[event.hazard_type] || { icon:"❓", label: event.hazard_type, color:"#64748b" };
  return (
    <div style={{
      background  : "#1e293b",
      border      : `1px solid ${cfg.color}`,
      borderRadius: 10,
      padding     : "12px 16px",
      marginBottom: 8,
    }}>
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:6 }}>
        <span style={{ fontSize:18 }}>{cfg.icon}</span>
        <span style={{ color: cfg.color, fontWeight:700, fontSize:13 }}>
          {cfg.label}
        </span>
        <span style={{
          marginLeft  : "auto",
          background  : SEVERITY_COLOR[event.severity] + "33",
          border      : `1px solid ${SEVERITY_COLOR[event.severity]}`,
          borderRadius: 12,
          color       : SEVERITY_COLOR[event.severity],
          fontSize    : 10,
          padding     : "2px 8px",
          fontWeight  : 700,
        }}>
          {event.severity}
        </span>
        {event.combined_alert && (
          <span style={{
            background  : "#7f1d1d",
            border      : "1px solid #dc2626",
            borderRadius: 12,
            color       : "#fca5a5",
            fontSize    : 10,
            padding     : "2px 8px",
            fontWeight  : 700,
          }}>
            COMBINED
          </span>
        )}
      </div>

      <div style={{ color:"#94a3b8", fontSize:12, lineHeight:1.6 }}>
        <span>Track #{event.track_id}</span>
        {event.zone_id && <span> · Zone: {event.zone_id}</span>}
        <span> · Conf: {(event.confidence * 100).toFixed(0)}%</span>
        <span> · {event.timestamp?.slice(11,19)}</span>
      </div>

      {event.landmark_data && (
        <div style={{
          marginTop   : 8,
          background  : "#0f172a",
          borderRadius: 6,
          padding     : "6px 10px",
          fontSize    : 11,
          color       : "#64748b",
          fontFamily  : "monospace",
        }}>
          {Object.entries(event.landmark_data).map(([k, v]) => (
            <div key={k}>
              <span style={{ color:"#475569" }}>{k}:</span>{" "}
              <span style={{ color:"#94a3b8" }}>
                {typeof v === "number" ? v.toFixed(3) : String(v)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PoseHazardPanel({ wsRef }) {
  const [hazards,   setHazards]   = useState([]);
  const [liveCount, setLiveCount] = useState({ total:0, critical:0 });
  const [loading,   setLoading]   = useState(true);

  // Load historical hazard events from DB
  const fetchHazards = async () => {
    try {
      const res  = await fetch(`${API_BASE}/pose-hazards?limit=30`);
      const data = await res.json();
      setHazards(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to load pose hazards:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHazards();
    const timer = setInterval(fetchHazards, 15000);
    return () => clearInterval(timer);
  }, []);

  // Live WebSocket updates
  useEffect(() => {
    if (!wsRef?.current) return;
    const handleMsg = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "pose_hazard") {
          setLiveCount({ total: msg.total, critical: msg.critical });
          fetchHazards();
        }
      } catch {}
    };
    wsRef.current.addEventListener("message", handleMsg);
    return () => wsRef.current?.removeEventListener("message", handleMsg);
  }, [wsRef]);

  const combined = hazards.filter((h) => h.combined_alert).length;
  const critical = hazards.filter((h) => h.severity === "CRITICAL").length;

  return (
    <div style={{ fontFamily:"system-ui", padding:"0 0 24px" }}>
      <h2 style={{ color:"#f1f5f9", fontSize:18, marginBottom:16 }}>
        Pose Hazard Detection
      </h2>

      {/* Stats */}
      <div style={{ display:"flex", gap:10, marginBottom:20, flexWrap:"wrap" }}>
        {[
          { label:"Total Events",    value: hazards.length,  color:"#94a3b8" },
          { label:"Critical",        value: critical,         color:"#dc2626" },
          { label:"Combined Alerts", value: combined,         color:"#7c3aed" },
          { label:"Live Total",      value: liveCount.total,  color:"#22c55e" },
        ].map(({ label, value, color }) => (
          <div
            key   = {label}
            style={{
              background  : "#1e293b",
              border      : "1px solid #334155",
              borderRadius: 10,
              padding     : "12px 18px",
              minWidth    : 110,
            }}
          >
            <div style={{ color, fontSize:11, marginBottom:4 }}>{label}</div>
            <div style={{ color:"#f1f5f9", fontSize:22, fontWeight:700 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Hazard type legend */}
      <div style={{ display:"flex", gap:8, marginBottom:16, flexWrap:"wrap" }}>
        {Object.entries(HAZARD_CONFIG).map(([type, cfg]) => (
          <div
            key   = {type}
            style={{
              background  : "#1e293b",
              border      : `1px solid ${cfg.color}`,
              borderRadius: 8,
              padding     : "4px 10px",
              display     : "flex",
              alignItems  : "center",
              gap         : 5,
            }}
          >
            <span style={{ fontSize:14 }}>{cfg.icon}</span>
            <span style={{ color: cfg.color, fontSize:11 }}>{cfg.label}</span>
          </div>
        ))}
      </div>

      {/* Events list */}
      <h3 style={{ color:"#94a3b8", fontSize:13, marginBottom:10 }}>
        Recent Hazard Events
      </h3>
      {loading ? (
        <div style={{ color:"#64748b" }}>Loading...</div>
      ) : hazards.length === 0 ? (
        <div style={{ color:"#475569", fontSize:13 }}>
          No pose hazards detected yet. MediaPipe is monitoring all frames.
        </div>
      ) : (
        hazards.map((h) => <HazardCard key={h.id} event={h} />)
      )}
    </div>
  );
}