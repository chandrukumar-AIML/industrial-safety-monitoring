import { useState, useEffect, useRef } from "react";

const SEVERITY_CONFIG = {
  CRITICAL: { bg: "#7f1d1d", border: "#dc2626", text: "#fca5a5", icon: "🚨" },
  HIGH    : { bg: "#7c2d12", border: "#ea580c", text: "#fdba74", icon: "⚠️" },
  MEDIUM  : { bg: "#713f12", border: "#ca8a04", text: "#fcd34d", icon: "⚠" },
  LOW     : { bg: "#14532d", border: "#16a34a", text: "#86efac", icon: "ℹ" },
};

export default function ZoneAlertBanner({ wsRef }) {
  const [alerts,  setAlerts]  = useState([]);
  const audioRef = useRef(null);

  useEffect(() => {
    if (!wsRef?.current) return;

    const handleMessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type !== "zone_alert") return;

        const alert = {
          id        : Date.now() + Math.random(),
          zone_id   : msg.zone_id,
          zone_name : msg.zone_name,
          zone_type : msg.zone_type,
          track_id  : msg.track_id,
          missing_ppe: msg.missing_ppe,
          severity  : msg.severity,
          timestamp : new Date().toLocaleTimeString(),
        };

        setAlerts((prev) => [alert, ...prev.slice(0, 4)]);

        // Auto-dismiss after 8 seconds
        setTimeout(() => {
          setAlerts((prev) => prev.filter((a) => a.id !== alert.id));
        }, 8000);

        // Play alert sound for CRITICAL/HIGH
        if (["CRITICAL", "HIGH"].includes(msg.severity) && audioRef.current) {
          audioRef.current.play().catch(() => {});
        }
      } catch {
        // ignore non-JSON messages
      }
    };

    wsRef.current.addEventListener("message", handleMessage);
    return () => wsRef.current?.removeEventListener("message", handleMessage);
  }, [wsRef]);

  if (alerts.length === 0) return null;

  return (
    <>
      {/* Inaudible audio alert */}
      <audio ref={audioRef} preload="auto">
        <source src="/alert.mp3" type="audio/mpeg" />
      </audio>

      {/* Alert stack — top-right fixed */}
      <div style={{
        position  : "fixed",
        top       : 80,
        right     : 20,
        zIndex    : 2000,
        display   : "flex",
        flexDirection: "column",
        gap       : 8,
        maxWidth  : 380,
      }}>
        {alerts.map((alert) => {
          const cfg = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.MEDIUM;
          return (
            <div
              key   = {alert.id}
              style={{
                background  : cfg.bg,
                border      : `1px solid ${cfg.border}`,
                borderRadius: 10,
                padding     : "12px 16px",
                animation   : "slideIn 0.3s ease",
              }}
            >
              <style>{`
                @keyframes slideIn {
                  from { transform: translateX(100%); opacity: 0; }
                  to   { transform: translateX(0);    opacity: 1; }
                }
              `}</style>

              <div style={{
                display     : "flex",
                alignItems  : "center",
                gap         : 8,
                marginBottom: 6,
              }}>
                <span style={{ fontSize: 18 }}>{cfg.icon}</span>
                <span style={{
                  color     : cfg.text,
                  fontWeight: 700,
                  fontSize  : 13,
                }}>
                  {alert.severity} — Zone Alert
                </span>
                <button
                  onClick = {() =>
                    setAlerts((prev) => prev.filter((a) => a.id !== alert.id))
                  }
                  style={{
                    marginLeft  : "auto",
                    background  : "transparent",
                    border      : "none",
                    color       : cfg.text,
                    cursor      : "pointer",
                    fontSize    : 16,
                    opacity     : 0.7,
                    padding     : 0,
                  }}
                >
                  ×
                </button>
              </div>

              <div style={{ color: cfg.text, fontSize: 12, lineHeight: 1.6 }}>
                <div>
                  <b>Zone:</b> {alert.zone_name} ({alert.zone_type})
                </div>
                <div>
                  <b>Worker ID:</b> {alert.track_id}
                </div>
                <div>
                  <b>Missing PPE:</b> {alert.missing_ppe.join(", ")}
                </div>
                <div style={{ opacity: 0.7, fontSize: 11, marginTop: 4 }}>
                  {alert.timestamp}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}