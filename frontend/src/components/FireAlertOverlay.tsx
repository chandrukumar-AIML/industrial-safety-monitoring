import { useState, useEffect, useRef } from "react";

/**
 * Full-screen fire emergency overlay.
 *
 * Listens to WebSocket fire_status messages.
 * When state = "FIRE" → shows red emergency overlay.
 * When state = "CLEARING" → shows amber countdown overlay.
 * When state = "NORMAL" → invisible.
 *
 * Usage: <FireAlertOverlay wsRef={wsRef} />
 */
export default function FireAlertOverlay({ wsRef }) {
  const [fireState,    setFireState]    = useState("NORMAL");
  const [fireData,     setFireData]     = useState(null);
  const [blinkOn,      setBlinkOn]      = useState(true);
  const audioRef = useRef(null);

  // Blink effect for emergency
  useEffect(() => {
    if (fireState !== "FIRE") return;
    const timer = setInterval(() => setBlinkOn((v) => !v), 500);
    return () => clearInterval(timer);
  }, [fireState]);

  // WebSocket listener
  useEffect(() => {
    if (!wsRef?.current) return;
    const handle = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type !== "fire_status") return;
        setFireState(msg.state);
        setFireData(msg);

        if (msg.state === "FIRE" && audioRef.current) {
          audioRef.current.play().catch(() => {});
        }
      } catch {}
    };
    wsRef.current.addEventListener("message", handle);
    return () => wsRef.current?.removeEventListener("message", handle);
  }, [wsRef]);

  // Not visible in normal state
  if (fireState === "NORMAL") return null;

  const isEmergency = fireState === "FIRE";
  const isClearing  = fireState === "CLEARING";
  const isSmokeOnly = fireState === "SMOKE";

  return (
    <>
      {/* Alarm audio */}
      <audio ref={audioRef} loop preload="auto">
        <source src="/fire-alarm.mp3" type="audio/mpeg" />
      </audio>

      {/* Emergency overlay */}
      <div
        style={{
          position        : "fixed",
          inset           : 0,
          zIndex          : 9999,
          pointerEvents   : isEmergency ? "auto" : "none",
          background      : isEmergency
            ? `rgba(220, 38, 38, ${blinkOn ? 0.25 : 0.1})`
            : isSmokeOnly
            ? "rgba(100, 100, 100, 0.15)"
            : "rgba(234, 88, 12, 0.15)",
          transition      : "background 0.25s",
          display         : "flex",
          alignItems      : isEmergency ? "flex-start" : "flex-end",
          justifyContent  : "center",
          padding         : isEmergency ? 0 : 20,
        }}
      >
        {isEmergency && (
          /* Full emergency banner */
          <div
            style={{
              width          : "100%",
              background     : blinkOn ? "#dc2626" : "#991b1b",
              padding        : "20px 32px",
              display        : "flex",
              alignItems     : "center",
              gap            : 16,
              transition     : "background 0.25s",
            }}
          >
            <span style={{ fontSize: 40 }}>🔥</span>
            <div style={{ flex: 1 }}>
              <div style={{
                color      : "#fff",
                fontWeight : 800,
                fontSize   : 24,
                fontFamily : "system-ui",
                letterSpacing: 2,
              }}>
                FIRE EMERGENCY — EVACUATE IMMEDIATELY
              </div>
              <div style={{
                color    : "rgba(255,255,255,0.8)",
                fontSize : 14,
                marginTop: 4,
                fontFamily:"system-ui",
              }}>
                {fireData?.fire_count || 0} fire detection(s) ·
                Confidence: {((fireData?.avg_confidence || 0) * 100).toFixed(0)}% ·
                Frame: #{fireData?.frame_idx}
              </div>
            </div>
            <div style={{
              background  : "rgba(0,0,0,0.3)",
              borderRadius: 12,
              padding     : "8px 16px",
              color       : "#fff",
              fontSize    : 13,
              fontFamily  : "system-ui",
              textAlign   : "center",
            }}>
              <div style={{ fontWeight:700, fontSize:18 }}>🚨 ALERT</div>
              <div>WhatsApp + Email sent</div>
            </div>
          </div>
        )}

        {isClearing && (
          /* Clearing countdown */
          <div style={{
            background  : "#7c2d12",
            borderRadius: 12,
            padding     : "12px 24px",
            color       : "#fed7aa",
            fontFamily  : "system-ui",
            fontSize    : 14,
            fontWeight  : 600,
            border      : "1px solid #ea580c",
          }}>
            ⚠️ Fire zone clearing — monitoring for {fireData?.clear_countdown || 30} more frames
          </div>
        )}

        {isSmokeOnly && (
          /* Smoke warning */
          <div style={{
            background  : "#1c1917",
            borderRadius: 12,
            padding     : "12px 24px",
            color       : "#d6d3d1",
            fontFamily  : "system-ui",
            fontSize    : 14,
            fontWeight  : 600,
            border      : "1px solid #78716c",
          }}>
            💨 Smoke detected ({fireData?.smoke_count || 0} detections) — monitoring for fire
          </div>
        )}
      </div>
    </>
  );
}