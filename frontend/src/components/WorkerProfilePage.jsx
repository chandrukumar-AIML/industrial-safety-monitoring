import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const RISK_CONFIG = {
  LOW     : { color: "#22c55e", bg: "#14532d", label: "Low Risk"      },
  HIGH    : { color: "#ea580c", bg: "#7c2d12", label: "High Risk"     },
  CRITICAL: { color: "#dc2626", bg: "#7f1d1d", label: "Critical Risk" },
};

const TREND_ICON = { worsening:"↑", stable:"→", improving:"↓" };
const TREND_COLOR= { worsening:"#dc2626", stable:"#94a3b8", improving:"#22c55e" };

// ── Risk Dashboard ────────────────────────────────────────────
function RiskDashboard({ dashboard }) {
  if (!dashboard) return null;
  return (
    <div style={{ display:"flex", gap:10, marginBottom:20, flexWrap:"wrap" }}>
      {[
        { label:"Total Workers", value:dashboard.total_workers, color:"#94a3b8" },
        { label:"High Risk",     value:dashboard.high_risk,     color:"#ea580c" },
        { label:"Critical",      value:dashboard.critical_risk, color:"#dc2626" },
        { label:"HR Alerted",    value:dashboard.hr_alerted,    color:"#7c3aed" },
      ].map(({ label, value, color }) => (
        <div key={label} style={{
          background:"#1e293b", border:"1px solid #334155",
          borderRadius:10, padding:"10px 16px", minWidth:110,
        }}>
          <div style={{ color, fontSize:11, marginBottom:2 }}>{label}</div>
          <div style={{ color:"#f1f5f9", fontSize:22, fontWeight:700 }}>{value}</div>
        </div>
      ))}
    </div>
  );
}

// ── Worker card ───────────────────────────────────────────────
function WorkerCard({ worker, onSelect, selected }) {
  const cfg = RISK_CONFIG[worker.risk_level] || RISK_CONFIG.LOW;
  return (
    <div
      onClick = {() => onSelect(worker)}
      style   = {{
        background  : selected ? "#1e3a5f" : "#1e293b",
        border      : `1px solid ${selected ? "#2563eb" : cfg.color + "55"}`,
        borderRadius: 10,
        padding     : "12px 14px",
        marginBottom: 8,
        cursor      : "pointer",
        display     : "flex",
        alignItems  : "center",
        gap         : 12,
      }}
    >
      {/* Avatar */}
      <div style={{
        width       : 42,
        height      : 42,
        borderRadius: "50%",
        background  : cfg.bg,
        display     : "flex",
        alignItems  : "center",
        justifyContent:"center",
        fontSize    : 18,
        flexShrink  : 0,
      }}>
        👷
      </div>

      <div style={{ flex:1, minWidth:0 }}>
        <div style={{
          color     : "#f1f5f9",
          fontWeight: 600,
          fontSize  : 13,
          display   : "flex",
          alignItems: "center",
          gap       : 8,
        }}>
          {worker.full_name}
          {worker.hr_alerted && (
            <span style={{
              background:"#7c3aed",color:"#e9d5ff",
              fontSize:9,padding:"1px 6px",borderRadius:20,fontWeight:700,
            }}>HR</span>
          )}
          {!worker.enrolled && (
            <span style={{
              background:"#334155",color:"#64748b",
              fontSize:9,padding:"1px 6px",borderRadius:20,
            }}>no face</span>
          )}
        </div>
        <div style={{ color:"#64748b", fontSize:11, marginTop:2 }}>
          {worker.department} · {worker.shift} · ID: {worker.worker_id}
        </div>
      </div>

      <div style={{ textAlign:"right" }}>
        <div style={{
          background:cfg.bg, border:`1px solid ${cfg.color}`,
          borderRadius:20, padding:"2px 8px",
          color:cfg.color, fontSize:10, fontWeight:700, marginBottom:4,
        }}>
          {cfg.label}
        </div>
        <div style={{ color:"#94a3b8", fontSize:11 }}>
          Score: {worker.risk_score.toFixed(1)}
        </div>
      </div>
    </div>
  );
}

// ── Worker detail panel ───────────────────────────────────────
function WorkerDetail({ worker }) {
  const [violations, setViolations] = useState([]);
  const [risk,       setRisk]       = useState(null);
  const [loading,    setLoading]    = useState(true);

  useEffect(() => {
    if (!worker) return;
    const load = async () => {
      setLoading(true);
      try {
        const [vRes, rRes] = await Promise.all([
          fetch(`${API_BASE}/workers/${worker.worker_id}/violations?limit=20`),
          fetch(`${API_BASE}/workers/${worker.worker_id}/risk`),
        ]);
        setViolations(await vRes.json());
        setRisk(await rRes.json());
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    };
    load();
  }, [worker?.worker_id]);

  if (!worker) return (
    <div style={{ color:"#475569", padding:40, textAlign:"center", fontSize:13 }}>
      Select a worker to view their profile
    </div>
  );

  const cfg = RISK_CONFIG[worker.risk_level] || RISK_CONFIG.LOW;

  return (
    <div>
      {/* Header */}
      <div style={{
        background:`linear-gradient(135deg, ${cfg.bg}, #1e293b)`,
        borderRadius:12, padding:"20px 20px 16px",
        border:`1px solid ${cfg.color}`,
        marginBottom:14,
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          <div style={{
            width:56, height:56, borderRadius:"50%",
            background:cfg.bg, border:`2px solid ${cfg.color}`,
            display:"flex", alignItems:"center",
            justifyContent:"center", fontSize:28,
          }}>
            👷
          </div>
          <div>
            <div style={{ color:"#f1f5f9", fontWeight:700, fontSize:18 }}>
              {worker.full_name}
            </div>
            <div style={{ color:"#94a3b8", fontSize:12, marginTop:2 }}>
              {worker.department} · {worker.shift} shift · {worker.role}
            </div>
            <div style={{ color:"#64748b", fontSize:11 }}>
              ID: {worker.worker_id}
            </div>
          </div>
          <div style={{ marginLeft:"auto", textAlign:"right" }}>
            <div style={{
              background:cfg.bg, border:`1px solid ${cfg.color}`,
              borderRadius:20, padding:"4px 12px",
              color:cfg.color, fontWeight:700, fontSize:12, marginBottom:4,
            }}>
              {cfg.label}
            </div>
            {risk && (
              <div style={{
                color: TREND_COLOR[risk.trend], fontSize:12, fontWeight:600,
              }}>
                {TREND_ICON[risk.trend]} {risk.trend}
              </div>
            )}
          </div>
        </div>

        {/* Risk score bar */}
        {risk && (
          <div style={{ marginTop:14 }}>
            <div style={{ display:"flex", justifyContent:"space-between",
              fontSize:11, color:"#94a3b8", marginBottom:4 }}>
              <span>Risk Score: {risk.risk_score.toFixed(1)}</span>
              <span>{risk.violation_count} violations (7 days)</span>
            </div>
            <div style={{
              background:"#0f172a", borderRadius:20,
              height:8, overflow:"hidden",
            }}>
              <div style={{
                height:"100%",
                width:`${Math.min(100, (risk.risk_score / 30) * 100)}%`,
                background:cfg.color,
                borderRadius:20,
                transition:"width 0.5s",
              }} />
            </div>
            {risk.top_classes.length > 0 && (
              <div style={{ marginTop:6, display:"flex", gap:5, flexWrap:"wrap" }}>
                <span style={{ color:"#64748b", fontSize:11 }}>Top violations:</span>
                {risk.top_classes.map((c) => (
                  <span key={c} style={{
                    background:"#1e293b", border:"1px solid #334155",
                    borderRadius:12, color:"#94a3b8", fontSize:10,
                    padding:"1px 8px",
                  }}>
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Violation timeline */}
      <h4 style={{ color:"#94a3b8", fontSize:13, marginBottom:8 }}>
        Violation Timeline
      </h4>
      {loading ? (
        <div style={{ color:"#64748b", fontSize:12 }}>Loading...</div>
      ) : violations.length === 0 ? (
        <div style={{ color:"#475569", fontSize:12 }}>
          No violations recorded for this worker.
        </div>
      ) : (
        <div style={{ maxHeight:320, overflowY:"auto" }}>
          {violations.map((v) => (
            <div key={v.id} style={{
              display     : "flex",
              gap         : 10,
              alignItems  : "flex-start",
              padding     : "8px 0",
              borderBottom: "1px solid #1e293b",
            }}>
              <div style={{
                width:8, height:8, borderRadius:"50%",
                background:v.acknowledged ? "#334155" : "#dc2626",
                marginTop:4, flexShrink:0,
              }} />
              <div style={{ flex:1 }}>
                <div style={{ color:"#f1f5f9", fontSize:12, fontWeight:600 }}>
                  {v.class_name}
                </div>
                <div style={{ color:"#64748b", fontSize:11, marginTop:1 }}>
                  {v.zone_id && `Zone: ${v.zone_id} · `}
                  {v.camera_id && `Cam: ${v.camera_id} · `}
                  {v.timestamp?.slice(0,16).replace("T"," ")} UTC
                </div>
              </div>
              {!v.acknowledged && (
                <span style={{
                  background:"#7f1d1d", color:"#fca5a5",
                  fontSize:9, padding:"1px 6px",
                  borderRadius:12, fontWeight:700,
                }}>
                  UNACK
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Enroll worker form ────────────────────────────────────────
function EnrollForm({ onClose, onSuccess }) {
  const [form, setForm] = useState({
    worker_id:"", full_name:"", department:"", shift:"morning", role:"worker",
  });
  const [photo,  setPhoto]  = useState(null);
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const fd = new FormData();
      Object.entries(form).forEach(([k,v]) => fd.append(k, v));
      if (photo) fd.append("photo", photo);

      const res = await fetch(`${API_BASE}/workers`, {
        method: "POST", body: fd,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create worker");
      }
      onSuccess();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    width:"100%", background:"#0f172a", border:"1px solid #334155",
    borderRadius:8, color:"#f1f5f9", padding:"7px 11px",
    fontSize:13, boxSizing:"border-box",
  };

  return (
    <div style={{
      position:"fixed", inset:0,
      background:"rgba(0,0,0,0.65)",
      display:"flex", alignItems:"center",
      justifyContent:"center", zIndex:1000,
    }}>
      <div style={{
        background:"#1e293b", borderRadius:14,
        padding:24, width:400, border:"1px solid #334155",
      }}>
        <h3 style={{ color:"#f1f5f9", margin:"0 0 16px", fontSize:16 }}>
          Enroll Worker
        </h3>

        {error && (
          <div style={{
            background:"#7f1d1d", borderRadius:8,
            padding:"8px 12px", color:"#fca5a5",
            fontSize:12, marginBottom:12,
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {[
            { label:"Worker ID",   key:"worker_id",  placeholder:"W001" },
            { label:"Full Name",   key:"full_name",  placeholder:"John Smith" },
            { label:"Department",  key:"department", placeholder:"Construction" },
            { label:"Role",        key:"role",       placeholder:"Site Worker" },
          ].map(({ label, key, placeholder }) => (
            <div key={key} style={{ marginBottom:10 }}>
              <label style={{ color:"#94a3b8", fontSize:11, display:"block", marginBottom:3 }}>
                {label}
              </label>
              <input
                required
                value       = {form[key]}
                onChange    = {(e) => setForm((f) => ({...f,[key]:e.target.value}))}
                placeholder = {placeholder}
                style       = {inputStyle}
              />
            </div>
          ))}

          <div style={{ marginBottom:10 }}>
            <label style={{ color:"#94a3b8", fontSize:11, display:"block", marginBottom:3 }}>
              Shift
            </label>
            <select
              value    = {form.shift}
              onChange = {(e) => setForm((f) => ({...f,shift:e.target.value}))}
              style    = {inputStyle}
            >
              {["morning","afternoon","night"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          <div style={{ marginBottom:14 }}>
            <label style={{ color:"#94a3b8", fontSize:11, display:"block", marginBottom:3 }}>
              Face Photo (optional — for face recognition)
            </label>
            <input
              type     = "file"
              accept   = "image/*"
              onChange = {(e) => setPhoto(e.target.files[0])}
              style    = {{ color:"#94a3b8", fontSize:12 }}
            />
            <div style={{ color:"#475569", fontSize:10, marginTop:3 }}>
              Photo will be face-blurred before storage (privacy compliance)
            </div>
          </div>

          <div style={{ display:"flex", gap:10 }}>
            <button
              type="submit"
              disabled={saving}
              style={{
                flex:1, background:"#2563eb", border:"none",
                borderRadius:8, color:"#fff", padding:"9px",
                cursor:saving?"wait":"pointer", fontWeight:600, fontSize:13,
              }}
            >
              {saving ? "Enrolling..." : "Enroll Worker"}
            </button>
            <button
              type="button"
              onClick={onClose}
              style={{
                background:"#334155", border:"none", borderRadius:8,
                color:"#f1f5f9", padding:"9px 16px",
                cursor:"pointer", fontSize:13,
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

// ── Main WorkerProfilePage ────────────────────────────────────
export default function WorkerProfilePage() {
  const [workers,    setWorkers]    = useState([]);
  const [selected,   setSelected]   = useState(null);
  const [dashboard,  setDashboard]  = useState(null);
  const [showEnroll, setShowEnroll] = useState(false);
  const [filter,     setFilter]     = useState("");
  const [loading,    setLoading]    = useState(true);

  const fetchAll = async () => {
    try {
      const [wRes, dRes] = await Promise.all([
        fetch(`${API_BASE}/workers`),
        fetch(`${API_BASE}/workers/dashboard/risk`),
      ]);
      setWorkers(await wRes.json());
      setDashboard(await dRes.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);
  useEffect(() => {
    const t = setInterval(fetchAll, 30000);
    return () => clearInterval(t);
  }, []);

  const filtered = workers.filter((w) =>
    !filter ||
    w.full_name.toLowerCase().includes(filter.toLowerCase()) ||
    w.worker_id.toLowerCase().includes(filter.toLowerCase()) ||
    (w.department || "").toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div style={{ fontFamily:"system-ui", padding:"0 0 24px" }}>
      <div style={{ display:"flex", alignItems:"center",
        gap:12, marginBottom:16, flexWrap:"wrap" }}>
        <h2 style={{ color:"#f1f5f9", fontSize:18, margin:0 }}>
          Worker Profiles
        </h2>
        <button
          onClick = {() => setShowEnroll(true)}
          style   = {{
            background:"#2563eb", border:"none", borderRadius:8,
            color:"#fff", padding:"6px 14px",
            cursor:"pointer", fontWeight:600, fontSize:13,
            marginLeft:"auto",
          }}
        >
          + Enroll Worker
        </button>
      </div>

      <RiskDashboard dashboard={dashboard} />

      {/* Top offenders quick list */}
      {dashboard?.top_offenders?.length > 0 && (
        <div style={{
          background:"#1e293b", borderRadius:10,
          padding:"10px 14px", marginBottom:16,
          border:"1px solid #dc262655",
        }}>
          <div style={{ color:"#dc2626", fontSize:11,
            fontWeight:700, marginBottom:8 }}>
            ⚠ Top Offenders This Week
          </div>
          <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
            {dashboard.top_offenders.map((w) => (
              <button
                key     = {w.worker_id}
                onClick = {() => setSelected(w)}
                style   = {{
                  background  :"#0f172a",
                  border      :`1px solid ${RISK_CONFIG[w.risk_level]?.color||"#334155"}`,
                  borderRadius: 20,
                  color       : "#f1f5f9",
                  padding     : "3px 12px",
                  cursor      : "pointer",
                  fontSize    : 12,
                }}
              >
                {w.full_name}
                <span style={{
                  marginLeft:6,
                  color:RISK_CONFIG[w.risk_level]?.color,
                  fontWeight:700,
                }}>
                  {w.risk_score.toFixed(0)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Search */}
      <input
        placeholder = "Search workers..."
        value       = {filter}
        onChange    = {(e) => setFilter(e.target.value)}
        style       = {{
          width:"100%", background:"#1e293b",
          border:"1px solid #334155", borderRadius:8,
          color:"#f1f5f9", padding:"8px 12px",
          fontSize:13, boxSizing:"border-box", marginBottom:12,
        }}
      />

      {/* Split view */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16 }}>
        {/* Worker list */}
        <div>
          <div style={{ color:"#94a3b8", fontSize:12, marginBottom:8 }}>
            {filtered.length} workers
          </div>
          {loading ? (
            <div style={{ color:"#64748b" }}>Loading...</div>
          ) : filtered.length === 0 ? (
            <div style={{ color:"#475569", fontSize:13 }}>
              No workers found. Click "Enroll Worker" to add profiles.
            </div>
          ) : (
            filtered.map((w) => (
              <WorkerCard
                key      = {w.worker_id}
                worker   = {w}
                onSelect = {setSelected}
                selected = {selected?.worker_id === w.worker_id}
              />
            ))
          )}
        </div>

        {/* Detail panel */}
        <WorkerDetail worker={selected} />
      </div>

      {showEnroll && (
        <EnrollForm
          onClose  = {() => setShowEnroll(false)}
          onSuccess= {fetchAll}
        />
      )}
    </div>
  );
}