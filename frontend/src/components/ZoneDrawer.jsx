import { useState, useRef, useEffect, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const ZONE_TYPE_CONFIG = {
  danger    : { color: "#ef4444", label: "Danger",     defaultPPE: ["hardhat","gloves","goggles"] },
  restricted: { color: "#f97316", label: "Restricted",  defaultPPE: ["hardhat"] },
  safe      : { color: "#22c55e", label: "Safe",        defaultPPE: [] },
};

// ── Canvas zone drawing ───────────────────────────────────────
function ZoneCanvas({ zones, onZoneCreated, frameWidth = 640, frameHeight = 360 }) {
  const canvasRef     = useRef(null);
  const [drawing,     setDrawing]     = useState(false);
  const [currentPoly, setCurrentPoly] = useState([]);   // [{x,y}] normalised
  const [mousePos,    setMousePos]    = useState(null);
  const [zoneType,    setZoneType]    = useState("danger");
  const [zoneName,    setZoneName]    = useState("");
  const [requiredPPE, setRequiredPPE] = useState(ZONE_TYPE_CONFIG.danger.defaultPPE);

  const PPE_OPTIONS = ["hardhat","gloves","goggles","boots","mask","suit"];

  // Convert canvas pixel → normalised [0,1]
  const toNorm = useCallback((px, py, canvas) => ({
    x: parseFloat((px / canvas.width).toFixed(4)),
    y: parseFloat((py / canvas.height).toFixed(4)),
  }), []);

  // Convert normalised → canvas pixel
  const toPx = useCallback((nx, ny, canvas) => ({
    x: nx * canvas.width,
    y: ny * canvas.height,
  }), []);

  // Draw everything on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx    = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw existing saved zones
    zones.forEach((zone) => {
      if (zone.polygon_norm.length < 2) return;
      const color = ZONE_TYPE_CONFIG[zone.zone_type]?.color || "#6366f1";
      ctx.beginPath();
      const first = toPx(zone.polygon_norm[0][0], zone.polygon_norm[0][1], canvas);
      ctx.moveTo(first.x, first.y);
      zone.polygon_norm.slice(1).forEach(([nx, ny]) => {
        const p = toPx(nx, ny, canvas);
        ctx.lineTo(p.x, p.y);
      });
      ctx.closePath();
      ctx.fillStyle   = color + "33";   // 20% opacity
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth   = 2;
      ctx.stroke();

      // Zone label
      const cx = zone.polygon_norm.reduce((s, p) => s + p[0], 0) / zone.polygon_norm.length;
      const cy = zone.polygon_norm.reduce((s, p) => s + p[1], 0) / zone.polygon_norm.length;
      const lp = toPx(cx, cy, canvas);
      ctx.fillStyle = "#fff";
      ctx.font      = "bold 12px system-ui";
      ctx.textAlign = "center";
      ctx.fillText(zone.zone_name, lp.x, lp.y);
    });

    // Draw in-progress polygon
    if (currentPoly.length > 0) {
      const color = ZONE_TYPE_CONFIG[zoneType]?.color || "#6366f1";
      ctx.beginPath();
      const fp = toPx(currentPoly[0].x, currentPoly[0].y, canvas);
      ctx.moveTo(fp.x, fp.y);
      currentPoly.slice(1).forEach((pt) => {
        const p = toPx(pt.x, pt.y, canvas);
        ctx.lineTo(p.x, p.y);
      });
      if (mousePos) ctx.lineTo(mousePos.x, mousePos.y);
      ctx.strokeStyle = color;
      ctx.lineWidth   = 2;
      ctx.setLineDash([6, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw vertex dots
      currentPoly.forEach((pt) => {
        const p = toPx(pt.x, pt.y, canvas);
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      });

      // Close hint — highlight first vertex
      if (currentPoly.length >= 3) {
        const fp2 = toPx(currentPoly[0].x, currentPoly[0].y, canvas);
        ctx.beginPath();
        ctx.arc(fp2.x, fp2.y, 9, 0, Math.PI * 2);
        ctx.strokeStyle = "#fff";
        ctx.lineWidth   = 2;
        ctx.stroke();
      }
    }
  }, [zones, currentPoly, mousePos, zoneType, toPx]);

  const handleCanvasClick = (e) => {
    if (!drawing) return;
    const canvas = canvasRef.current;
    const rect   = canvas.getBoundingClientRect();
    const px     = e.clientX - rect.left;
    const py     = e.clientY - rect.top;
    const norm   = toNorm(px, py, canvas);

    // Close polygon if click near first vertex
    if (currentPoly.length >= 3) {
      const fp = toPx(currentPoly[0].x, currentPoly[0].y, canvas);
      const dist = Math.hypot(px - fp.x, py - fp.y);
      if (dist < 12) {
        handleFinishPolygon();
        return;
      }
    }
    setCurrentPoly((prev) => [...prev, norm]);
  };

  const handleMouseMove = (e) => {
    if (!drawing) return;
    const canvas = canvasRef.current;
    const rect   = canvas.getBoundingClientRect();
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  const handleFinishPolygon = () => {
    if (currentPoly.length < 3) return;
    onZoneCreated({
      polygon_norm: currentPoly,
      zone_type   : zoneType,
      zone_name   : zoneName || `Zone ${Date.now()}`,
      required_ppe: requiredPPE,
      color_hex   : ZONE_TYPE_CONFIG[zoneType].color,
    });
    setCurrentPoly([]);
    setDrawing(false);
    setZoneName("");
  };

  const cancelDrawing = () => {
    setCurrentPoly([]);
    setDrawing(false);
  };

  return (
    <div style={{ fontFamily: "system-ui" }}>
      {/* Controls */}
      <div style={{
        display       : "flex",
        gap           : 10,
        alignItems    : "center",
        marginBottom  : 10,
        flexWrap      : "wrap",
      }}>
        <select
          value    = {zoneType}
          onChange = {(e) => {
            setZoneType(e.target.value);
            setRequiredPPE(ZONE_TYPE_CONFIG[e.target.value].defaultPPE);
          }}
          style={{
            background  : "#1e293b",
            border      : `2px solid ${ZONE_TYPE_CONFIG[zoneType].color}`,
            borderRadius: 8,
            color       : "#f1f5f9",
            padding     : "6px 12px",
            fontSize    : 13,
          }}
        >
          {Object.entries(ZONE_TYPE_CONFIG).map(([type, cfg]) => (
            <option key={type} value={type}>{cfg.label}</option>
          ))}
        </select>

        <input
          placeholder = "Zone name..."
          value       = {zoneName}
          onChange    = {(e) => setZoneName(e.target.value)}
          style={{
            background  : "#1e293b",
            border      : "1px solid #334155",
            borderRadius: 8,
            color       : "#f1f5f9",
            padding     : "6px 12px",
            fontSize    : 13,
            width       : 160,
          }}
        />

        {!drawing ? (
          <button
            onClick={() => setDrawing(true)}
            style={{
              background  : ZONE_TYPE_CONFIG[zoneType].color,
              border      : "none",
              borderRadius: 8,
              color       : "#fff",
              padding     : "6px 14px",
              cursor      : "pointer",
              fontWeight  : 600,
              fontSize    : 13,
            }}
          >
            ✏ Draw Zone
          </button>
        ) : (
          <>
            <button
              onClick = {handleFinishPolygon}
              disabled= {currentPoly.length < 3}
              style={{
                background  : "#16a34a",
                border      : "none",
                borderRadius: 8,
                color       : "#fff",
                padding     : "6px 14px",
                cursor      : currentPoly.length < 3 ? "not-allowed" : "pointer",
                fontWeight  : 600,
                fontSize    : 13,
              }}
            >
              ✓ Save ({currentPoly.length} pts)
            </button>
            <button
              onClick = {cancelDrawing}
              style={{
                background  : "#374151",
                border      : "none",
                borderRadius: 8,
                color       : "#f1f5f9",
                padding     : "6px 14px",
                cursor      : "pointer",
                fontSize    : 13,
              }}
            >
              ✕ Cancel
            </button>
          </>
        )}
      </div>

      {/* PPE requirements selector */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
        <span style={{ color: "#64748b", fontSize: 12, alignSelf: "center" }}>
          Required PPE:
        </span>
        {PPE_OPTIONS.map((ppe) => (
          <button
            key     = {ppe}
            onClick = {() => setRequiredPPE((prev) =>
              prev.includes(ppe) ? prev.filter((p) => p !== ppe) : [...prev, ppe]
            )}
            style={{
              background  : requiredPPE.includes(ppe) ? "#2563eb" : "#1e293b",
              border      : `1px solid ${requiredPPE.includes(ppe) ? "#2563eb" : "#334155"}`,
              borderRadius: 16,
              color       : "#f1f5f9",
              padding     : "3px 10px",
              cursor      : "pointer",
              fontSize    : 11,
              fontWeight  : requiredPPE.includes(ppe) ? 600 : 400,
            }}
          >
            {ppe}
          </button>
        ))}
      </div>

      {/* Canvas */}
      <div style={{ position: "relative", display: "inline-block" }}>
        <canvas
          ref         = {canvasRef}
          width       = {frameWidth}
          height      = {frameHeight}
          onClick     = {handleCanvasClick}
          onMouseMove = {handleMouseMove}
          style={{
            background  : "#0f172a",
            borderRadius: 10,
            cursor      : drawing ? "crosshair" : "default",
            border      : `1px solid #334155`,
            maxWidth    : "100%",
          }}
        />
        {drawing && (
          <div style={{
            position  : "absolute",
            top       : 8,
            left      : 8,
            background: "rgba(0,0,0,0.7)",
            color     : "#f1f5f9",
            fontSize  : 11,
            padding   : "4px 10px",
            borderRadius: 6,
          }}>
            Click to add points · Click near first point to close
          </div>
        )}
      </div>
    </div>
  );
}

// ── Zone management panel ─────────────────────────────────────
export default function ZoneDrawer() {
  const [zones,   setZones]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [saving,  setSaving]  = useState(false);

  const fetchZones = async () => {
    try {
      const res  = await fetch(`${API_BASE}/zones`);
      const data = await res.json();
      setZones(data);
    } catch (err) {
      setError("Failed to load zones");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchZones(); }, []);

  const handleZoneCreated = async (zoneData) => {
    setSaving(true);
    try {
      const zoneId = `zone-${Date.now()}`;
      const payload = {
        zone_id          : zoneId,
        zone_name        : zoneData.zone_name,
        zone_type        : zoneData.zone_type,
        polygon_norm     : zoneData.polygon_norm.map(({ x, y }) => ({ x, y })),
        required_ppe     : zoneData.required_ppe,
        alert_enabled    : true,
        dwell_threshold_s: 2.0,
        color_hex        : zoneData.color_hex,
      };

      const res = await fetch(`${API_BASE}/zones`, {
        method  : "POST",
        headers : { "Content-Type": "application/json" },
        body    : JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Save failed");
      }

      await fetchZones();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteZone = async (zoneId) => {
    if (!confirm(`Delete zone "${zoneId}"?`)) return;
    await fetch(`${API_BASE}/zones/${zoneId}`, { method: "DELETE" });
    await fetchZones();
  };

  return (
    <div style={{ padding: "0 0 24px", fontFamily: "system-ui" }}>
      <h2 style={{ color: "#f1f5f9", marginBottom: 16, fontSize: 18 }}>
        Zone Configuration
      </h2>

      {error && (
        <div style={{
          background  : "#7f1d1d",
          border      : "1px solid #dc2626",
          borderRadius: 8,
          padding     : "10px 14px",
          color       : "#fca5a5",
          marginBottom: 14,
          fontSize    : 13,
        }}>
          {error}
        </div>
      )}

      {/* Canvas drawing area */}
      <div style={{
        background  : "#1e293b",
        borderRadius: 12,
        padding     : 16,
        marginBottom: 20,
      }}>
        <ZoneCanvas
          zones          = {zones}
          onZoneCreated  = {handleZoneCreated}
          frameWidth     = {640}
          frameHeight    = {360}
        />
        {saving && (
          <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 8 }}>
            Saving zone...
          </div>
        )}
      </div>

      {/* Existing zones list */}
      <h3 style={{ color: "#94a3b8", fontSize: 14, marginBottom: 10 }}>
        Active Zones ({zones.length})
      </h3>

      {loading ? (
        <div style={{ color: "#64748b" }}>Loading...</div>
      ) : zones.length === 0 ? (
        <div style={{ color: "#475569", fontSize: 13 }}>
          No zones configured. Draw a zone above to get started.
        </div>
      ) : (
        zones.map((zone) => {
          const cfg   = ZONE_TYPE_CONFIG[zone.zone_type];
          return (
            <div
              key   = {zone.zone_id}
              style={{
                background  : "#1e293b",
                border      : `1px solid ${cfg?.color || "#334155"}`,
                borderRadius: 10,
                padding     : "12px 16px",
                marginBottom: 8,
                display     : "flex",
                alignItems  : "center",
                gap         : 12,
              }}
            >
              <div
                style={{
                  width       : 12,
                  height      : 12,
                  borderRadius: "50%",
                  background  : cfg?.color || "#6366f1",
                  flexShrink  : 0,
                }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ color: "#f1f5f9", fontWeight: 600, fontSize: 13 }}>
                  {zone.zone_name}
                </div>
                <div style={{ color: "#64748b", fontSize: 11, marginTop: 2 }}>
                  {cfg?.label} · {zone.polygon_norm.length} vertices ·
                  PPE: {zone.required_ppe.length > 0
                    ? zone.required_ppe.join(", ")
                    : "none required"}
                </div>
              </div>
              <button
                onClick = {() => handleDeleteZone(zone.zone_id)}
                style={{
                  background  : "transparent",
                  border      : "1px solid #475569",
                  borderRadius: 6,
                  color       : "#94a3b8",
                  padding     : "4px 10px",
                  cursor      : "pointer",
                  fontSize    : 12,
                }}
              >
                Delete
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}