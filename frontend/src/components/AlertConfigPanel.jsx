import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const PPE_OPTIONS   = ["hardhat","gloves","goggles","boots","mask","suit"];
const ROLE_OPTIONS  = ["manager","safety_officer","supervisor","hr"];

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background  : "#1e293b",
      border      : "1px solid #334155",
      borderRadius: 10,
      padding     : "12px 18px",
      minWidth    : 120,
    }}>
      <div style={{ color: color || "#94a3b8", fontSize: 11, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ color: "#f1f5f9", fontSize: 22, fontWeight: 700 }}>
        {value}
      </div>
    </div>
  );
}

export default function AlertConfigPanel() {
  const [recipients, setRecipients] = useState([]);
  const [stats,      setStats]      = useState(null);
  const [logs,       setLogs]       = useState([]);
  const [showForm,   setShowForm]   = useState(false);
  const [testing,    setTesting]    = useState(null);
  const [form, setForm] = useState({
    name            : "",
    role            : "manager",
    email           : "",
    whatsapp_number : "",
    notify_critical : true,
    notify_high     : true,
    notify_medium   : false,
    notify_low      : false,
  });

  const fetchAll = async () => {
    try {
      const [rRes, sRes, lRes] = await Promise.all([
        fetch(`${API_BASE}/alert-config/recipients`),
        fetch(`${API_BASE}/alert-config/stats`),
        fetch(`${API_BASE}/alert-config/logs?limit=20`),
      ]);
      if (rRes.ok) setRecipients(await rRes.json());
      if (sRes.ok) setStats(await sRes.json());
      if (lRes.ok) setLogs(await lRes.json());
    } catch {
      // Backend offline — keep empty state, no crash
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      email           : form.email           || null,
      whatsapp_number : form.whatsapp_number  || null,
    };
    await fetch(`${API_BASE}/alert-config/recipients`, {
      method  : "POST",
      headers : { "Content-Type": "application/json" },
      body    : JSON.stringify(payload),
    });
    setShowForm(false);
    setForm({
      name:"",role:"manager",email:"",whatsapp_number:"",
      notify_critical:true,notify_high:true,
      notify_medium:false,notify_low:false,
    });
    await fetchAll();
  };

  const handleDelete = async (id) => {
    if (!confirm("Remove this recipient?")) return;
    await fetch(`${API_BASE}/alert-config/recipients/${id}`, { method: "DELETE" });
    await fetchAll();
  };

  const handleTest = async (id) => {
    setTesting(id);
    await fetch(`${API_BASE}/alert-config/test?recipient_id=${id}`, { method: "POST" });
    setTimeout(() => setTesting(null), 3000);
  };

  const STATUS_COLOR = { sent:"#22c55e", throttled:"#ca8a04", failed:"#dc2626" };

  return (
    <div style={{ fontFamily:"system-ui", padding:"0 0 24px" }}>
      <h2 style={{ color:"#f1f5f9", fontSize:18, marginBottom:16 }}>
        Alert Configuration
      </h2>

      {/* Stats */}
      {stats && (
        <div style={{ display:"flex", gap:10, marginBottom:20, flexWrap:"wrap" }}>
          <StatCard label="Sent"       value={stats.total_sent}      color="#22c55e" />
          <StatCard label="Throttled"  value={stats.total_throttled} color="#ca8a04" />
          <StatCard label="Failed"     value={stats.total_failed}    color="#dc2626" />
          {Object.entries(stats.by_channel || {}).map(([ch, cnt]) => (
            <StatCard key={ch} label={ch.toUpperCase()} value={cnt} />
          ))}
        </div>
      )}

      {/* Add recipient button */}
      <button
        onClick = {() => setShowForm((v) => !v)}
        style={{
          background  : showForm ? "#334155" : "#f59e0b",
          border      : "none",
          borderRadius: 8,
          color       : showForm ? "#e2e8f0" : "#0f172a",
          padding     : "8px 16px",
          cursor      : "pointer",
          fontWeight  : 600,
          fontSize    : 13,
          marginBottom: 16,
        }}
      >
        {showForm ? "✕ Cancel" : "+ Add Recipient"}
      </button>

      {/* Add recipient form */}
      {showForm && (
        <form
          onSubmit = {handleSave}
          style={{
            background  : "#1e293b",
            borderRadius: 12,
            padding     : 20,
            marginBottom: 20,
            border      : "1px solid #334155",
          }}
        >
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
            {[
              { label:"Name",             key:"name",            type:"text" },
              { label:"WhatsApp (+E.164)",key:"whatsapp_number", type:"text" },
              { label:"Email",            key:"email",           type:"email"},
            ].map(({ label, key, type }) => (
              <div key={key}>
                <label style={{ color:"#94a3b8", fontSize:11, display:"block", marginBottom:4 }}>
                  {label}
                </label>
                <input
                  type      = {type}
                  value     = {form[key]}
                  onChange  = {(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  style={{
                    width       : "100%",
                    background  : "#0f172a",
                    border      : "1px solid #334155",
                    borderRadius: 8,
                    color       : "#f1f5f9",
                    padding     : "8px 12px",
                    fontSize    : 13,
                    boxSizing   : "border-box",
                  }}
                />
              </div>
            ))}

            <div>
              <label style={{ color:"#94a3b8", fontSize:11, display:"block", marginBottom:4 }}>
                Role
              </label>
              <select
                value    = {form.role}
                onChange = {(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                style={{
                  width       : "100%",
                  background  : "#0f172a",
                  border      : "1px solid #334155",
                  borderRadius: 8,
                  color       : "#f1f5f9",
                  padding     : "8px 12px",
                  fontSize    : 13,
                }}
              >
                {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>

          {/* Severity subscriptions */}
          <div style={{ marginTop:14 }}>
            <label style={{ color:"#94a3b8", fontSize:11, display:"block", marginBottom:8 }}>
              Notify on severity:
            </label>
            <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
              {[
                { key:"notify_critical", label:"CRITICAL", color:"#dc2626" },
                { key:"notify_high",     label:"HIGH",     color:"#ea580c" },
                { key:"notify_medium",   label:"MEDIUM",   color:"#ca8a04" },
                { key:"notify_low",      label:"LOW",      color:"#16a34a" },
              ].map(({ key, label, color }) => (
                <button
                  key     = {key}
                  type    = "button"
                  onClick = {() => setForm((f) => ({ ...f, [key]: !f[key] }))}
                  style={{
                    background  : form[key] ? color + "33" : "#0f172a",
                    border      : `1px solid ${form[key] ? color : "#334155"}`,
                    borderRadius: 8,
                    color       : form[key] ? color : "#64748b",
                    padding     : "5px 12px",
                    cursor      : "pointer",
                    fontSize    : 12,
                    fontWeight  : form[key] ? 700 : 400,
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <button
            type  = "submit"
            style={{
              marginTop   : 16,
              background  : "#2563eb",
              border      : "none",
              borderRadius: 8,
              color       : "#fff",
              padding     : "8px 20px",
              cursor      : "pointer",
              fontWeight  : 600,
              fontSize    : 13,
            }}
          >
            Save Recipient
          </button>
        </form>
      )}

      {/* Recipients list */}
      <h3 style={{ color:"#94a3b8", fontSize:13, marginBottom:10 }}>
        Active Recipients ({recipients.length})
      </h3>
      {recipients.map((r) => (
        <div
          key   = {r.id}
          style={{
            background  : "#1e293b",
            border      : "1px solid #334155",
            borderRadius: 10,
            padding     : "12px 16px",
            marginBottom: 8,
            display     : "flex",
            alignItems  : "center",
            gap         : 12,
          }}
        >
          <div style={{ flex:1 }}>
            <div style={{ color:"#f1f5f9", fontWeight:600, fontSize:13 }}>
              {r.name}
              <span style={{ color:"#64748b", fontSize:11, marginLeft:8 }}>
                {r.role}
              </span>
            </div>
            <div style={{ color:"#64748b", fontSize:11, marginTop:3, display:"flex", gap:10 }}>
              {r.email          && <span>✉ {r.email}</span>}
              {r.whatsapp_number && <span>💬 {r.whatsapp_number}</span>}
            </div>
            <div style={{ display:"flex", gap:5, marginTop:6 }}>
              {[
                { key:"notify_critical", label:"CRITICAL", color:"#dc2626" },
                { key:"notify_high",     label:"HIGH",     color:"#ea580c" },
                { key:"notify_medium",   label:"MEDIUM",   color:"#ca8a04" },
                { key:"notify_low",      label:"LOW",      color:"#16a34a" },
              ].filter(({ key }) => r[key]).map(({ label, color }) => (
                <span
                  key   = {label}
                  style={{
                    background  : color + "22",
                    border      : `1px solid ${color}`,
                    borderRadius: 12,
                    color,
                    fontSize    : 10,
                    padding     : "1px 8px",
                    fontWeight  : 600,
                  }}
                >
                  {label}
                </span>
              ))}
            </div>
          </div>

          <button
            onClick   = {() => handleTest(r.id)}
            disabled  = {testing === r.id}
            style={{
              background  : testing === r.id ? "#16a34a" : "#334155",
              border      : "none",
              borderRadius: 8,
              color       : "#f1f5f9",
              padding     : "5px 12px",
              cursor      : "pointer",
              fontSize    : 12,
            }}
          >
            {testing === r.id ? "✓ Sent!" : "Test"}
          </button>

          <button
            onClick = {() => handleDelete(r.id)}
            style={{
              background  : "transparent",
              border      : "1px solid #475569",
              borderRadius: 8,
              color       : "#94a3b8",
              padding     : "5px 10px",
              cursor      : "pointer",
              fontSize    : 12,
            }}
          >
            Remove
          </button>
        </div>
      ))}

      {/* Recent send log */}
      <h3 style={{ color:"#94a3b8", fontSize:13, margin:"20px 0 10px" }}>
        Recent Sends
      </h3>
      <div style={{
        background  : "#1e293b",
        borderRadius: 10,
        overflow    : "hidden",
        border      : "1px solid #334155",
      }}>
        {logs.slice(0, 10).map((log, i) => (
          <div
            key   = {log.id}
            style={{
              padding     : "8px 14px",
              display     : "flex",
              gap         : 10,
              alignItems  : "center",
              borderBottom: i < 9 ? "1px solid #1e293b" : "none",
              background  : i % 2 ? "#1a2639" : "transparent",
            }}
          >
            <span style={{
              color    : STATUS_COLOR[log.status] || "#64748b",
              fontSize : 11,
              minWidth : 60,
              fontWeight: 600,
            }}>
              {log.status?.toUpperCase()}
            </span>
            <span style={{ color:"#94a3b8", fontSize:11, minWidth:60 }}>
              {log.alert_type || "—"}
            </span>
            <span style={{ color:"#64748b", fontSize:11, flex:1 }}>
              {log.zone_id} · Track #{log.track_id} · {log.severity}
            </span>
            <span style={{ color:"#475569", fontSize:10 }}>
              {log.sent_at?.slice(11,19)}
            </span>
          </div>
        ))}
        {logs.length === 0 && (
          <div style={{ padding:"20px 14px", color:"#475569", fontSize:13, textAlign:"center" }}>
            No alerts sent yet
          </div>
        )}
      </div>
    </div>
  );
}