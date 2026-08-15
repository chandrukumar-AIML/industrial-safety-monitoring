import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STAGE_CONFIG = {
  production : { color:"#22c55e", bg:"#14532d", icon:"🟢" },
  canary     : { color:"#f59e0b", bg:"#713f12", icon:"🐦" },
  staging    : { color:"#6366f1", bg:"#312e81", icon:"🔵" },
  archived   : { color:"#475569", bg:"#1e293b", icon:"⬛" },
  None       : { color:"#334155", bg:"#0f172a", icon:"○"  },
};

function ModelVersionCard({ model }) {
  const cfg = STAGE_CONFIG[model.stage?.toLowerCase()] || STAGE_CONFIG.None;
  return (
    <div style={{
      background  : "#1e293b",
      border      : `1px solid ${cfg.color}44`,
      borderLeft  : `3px solid ${cfg.color}`,
      borderRadius: 8,
      padding     : "10px 14px",
      marginBottom: 6,
      display     : "flex",
      alignItems  : "center",
      gap         : 12,
    }}>
      <span style={{ fontSize:18 }}>{cfg.icon}</span>
      <div style={{ flex:1 }}>
        <div style={{ color:"#f1f5f9", fontWeight:600, fontSize:13 }}>
          v{model.version}
          <span style={{
            marginLeft:8, color:cfg.color, fontSize:11, fontWeight:400,
          }}>
            {model.stage}
          </span>
        </div>
        <div style={{ color:"#64748b", fontSize:11, marginTop:2 }}>
          mAP@0.5: {model.map50 ? model.map50.toFixed(4) : "—"}
          {model.notes && ` · ${model.notes.slice(0,40)}`}
        </div>
      </div>
      <div style={{ color:"#475569", fontSize:10, textAlign:"right" }}>
        {model.created_at?.slice(0,10)}
      </div>
    </div>
  );
}

function CanaryStatus({ status }) {
  if (!status?.active) return (
    <div style={{
      background:"#0f172a", borderRadius:8,
      padding:"12px 16px", color:"#475569", fontSize:13,
      border:"1px solid #1e293b",
    }}>
      No active canary deployment.
    </div>
  );

  const pct = (status.canary_frames / Math.max(1,
    parseInt(import.meta.env.VITE_CANARY_MIN_FRAMES || "1000")
  ) * 100).toFixed(0);

  return (
    <div style={{
      background  : "#1e293b",
      border      : "1px solid #f59e0b44",
      borderRadius: 10,
      padding     : "16px 18px",
    }}>
      <div style={{
        display:"flex", alignItems:"center",
        gap:10, marginBottom:12,
      }}>
        <span style={{ fontSize:20 }}>🐦</span>
        <span style={{ color:"#f59e0b", fontWeight:700, fontSize:14 }}>
          Canary Active — v{status.canary_version}
        </span>
        <span style={{ color:"#64748b", fontSize:12 }}>
          vs prod v{status.production_version}
        </span>
        <span style={{
          marginLeft:"auto",
          background:"#713f12", border:"1px solid #f59e0b",
          borderRadius:20, color:"#fcd34d",
          fontSize:11, padding:"2px 10px", fontWeight:700,
        }}>
          {status.canary_pct}% traffic
        </span>
      </div>

      {/* Progress bar */}
      <div style={{ marginBottom:10 }}>
        <div style={{
          display:"flex", justifyContent:"space-between",
          fontSize:11, color:"#94a3b8", marginBottom:4,
        }}>
          <span>Canary frames: {status.canary_frames.toLocaleString()}</span>
          <span>Minimum: {(1000).toLocaleString()}</span>
        </div>
        <div style={{
          background:"#0f172a", borderRadius:20, height:8, overflow:"hidden",
        }}>
          <div style={{
            height:"100%",
            width:`${Math.min(100, pct)}%`,
            background: parseInt(pct) >= 100 ? "#22c55e" : "#f59e0b",
            borderRadius:20, transition:"width 1s",
          }} />
        </div>
        {status.evaluation_ready && (
          <div style={{
            marginTop:6, color:"#22c55e", fontSize:11, fontWeight:600,
          }}>
            ✓ Ready for evaluation
          </div>
        )}
      </div>

      <div style={{ color:"#64748b", fontSize:11 }}>
        Total frames: {status.total_frames.toLocaleString()} ·
        Prod frames: {status.prod_frames.toLocaleString()}
      </div>
    </div>
  );
}

function DeploymentRow({ dep }) {
  const cfg = STAGE_CONFIG[dep.stage] || STAGE_CONFIG.archived;
  return (
    <div style={{
      display:"flex", alignItems:"center", gap:10,
      padding:"8px 12px", background:"#1e293b",
      borderRadius:8, marginBottom:4,
      border:`1px solid ${cfg.color}22`,
    }}>
      <span style={{ fontSize:14 }}>{cfg.icon}</span>
      <div style={{ flex:1 }}>
        <div style={{ color:"#f1f5f9", fontSize:12, fontWeight:600 }}>
          v{dep.model_version}
          <span style={{ color:cfg.color, marginLeft:8, fontSize:11 }}>
            {dep.stage}
          </span>
        </div>
        {dep.rollback_reason && (
          <div style={{ color:"#dc2626", fontSize:10, marginTop:1 }}>
            ↩ {dep.rollback_reason.slice(0,60)}
          </div>
        )}
      </div>
      <div style={{ color:"#475569", fontSize:10, textAlign:"right" }}>
        <div>mAP: {dep.map50?.toFixed(4) ?? "—"}</div>
        <div>{dep.created_at?.slice(0,10)}</div>
      </div>
    </div>
  );
}

export default function MLOpsPanel() {
  const [models,      setModels]      = useState([]);
  const [deployments, setDeployments] = useState([]);
  const [canary,      setCanary]      = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [actionMsg,   setActionMsg]   = useState(null);
  const [startForm,   setStartForm]   = useState(false);
  const [canaryVersion, setCanaryVersion] = useState("");

  const fetchAll = async () => {
    try {
      const [mRes, dRes, cRes] = await Promise.all([
        fetch(`${API_BASE}/mlops/models`),
        fetch(`${API_BASE}/mlops/deployments?limit=10`),
        fetch(`${API_BASE}/mlops/canary/status`),
      ]);
      setModels(await mRes.json());
      setDeployments(await dRes.json());
      setCanary(await cRes.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);
  useEffect(() => {
    const t = setInterval(fetchAll, 15000);
    return () => clearInterval(t);
  }, []);

  const action = async (path, body = {}) => {
    setActionMsg("Processing…");
    try {
      const res  = await fetch(`${API_BASE}/mlops/${path}`, {
        method  : "POST",
        headers : { "Content-Type": "application/json" },
        body    : JSON.stringify(body),
      });
      const data = await res.json();
      setActionMsg(JSON.stringify(data, null, 2));
      await fetchAll();
    } catch (e) {
      setActionMsg(`Error: ${e.message}`);
    }
  };

  const stagingModels     = models.filter((m) => m.stage === "Staging");
  const productionModels  = models.filter((m) => m.stage === "Production");
  const archivedModels    = models.filter((m) => m.stage === "Archived");

  return (
    <div style={{ fontFamily:"system-ui", padding:"0 0 24px" }}>
      <h2 style={{ color:"#f1f5f9", fontSize:18, marginBottom:16 }}>
        MLOps — Model Registry & Canary Deploy
      </h2>

      {/* Canary status */}
      <h3 style={{ color:"#94a3b8", fontSize:13, marginBottom:8 }}>
        Active Canary
      </h3>
      <CanaryStatus status={canary} />

      {/* Canary actions */}
      <div style={{ display:"flex", gap:8, margin:"12px 0 20px", flexWrap:"wrap" }}>
        <button
          onClick = {() => setStartForm((v) => !v)}
          style   = {{
            background:"#6366f1", border:"none", borderRadius:8,
            color:"#fff", padding:"6px 14px",
            cursor:"pointer", fontWeight:600, fontSize:12,
          }}
        >
          🐦 Start Canary
        </button>

        {canary?.active && (
          <>
            <button
              onClick = {() => action("canary/evaluate", {
                deployment_id: canary.deployment_id
              })}
              style   = {{
                background:"#0ea5e9", border:"none", borderRadius:8,
                color:"#fff", padding:"6px 14px",
                cursor:"pointer", fontSize:12,
              }}
            >
              ⚡ Evaluate Now
            </button>
            <button
              onClick = {() => action("promote", {
                deployment_id: canary.deployment_id,
                reason: "Manual promotion",
              })}
              style   = {{
                background:"#22c55e", border:"none", borderRadius:8,
                color:"#fff", padding:"6px 14px",
                cursor:"pointer", fontSize:12,
              }}
            >
              ✅ Promote
            </button>
            <button
              onClick = {() => action("rollback", {
                deployment_id: canary.deployment_id,
                reason: "Manual rollback",
              })}
              style   = {{
                background:"#dc2626", border:"none", borderRadius:8,
                color:"#fff", padding:"6px 14px",
                cursor:"pointer", fontSize:12,
              }}
            >
              ↩ Rollback
            </button>
          </>
        )}
      </div>

      {/* Start canary form */}
      {startForm && (
        <div style={{
          background:"#1e293b", borderRadius:10,
          padding:14, marginBottom:16,
          border:"1px solid #334155",
        }}>
          <div style={{ display:"flex", gap:8, alignItems:"center" }}>
            <input
              placeholder = "Model version (e.g. 12)"
              value       = {canaryVersion}
              onChange    = {(e) => setCanaryVersion(e.target.value)}
              style       = {{
                flex:1, background:"#0f172a",
                border:"1px solid #334155", borderRadius:8,
                color:"#f1f5f9", padding:"7px 11px", fontSize:13,
              }}
            />
            <button
              onClick = {() => {
                action("canary/start", { canary_version: canaryVersion });
                setStartForm(false);
              }}
              style   = {{
                background:"#6366f1", border:"none", borderRadius:8,
                color:"#fff", padding:"7px 14px",
                cursor:"pointer", fontWeight:600, fontSize:13,
              }}
            >
              Start
            </button>
          </div>
        </div>
      )}

      {actionMsg && (
        <pre style={{
          background:"#0f172a", borderRadius:8,
          padding:"10px 14px", color:"#94a3b8",
          fontSize:11, marginBottom:16,
          maxHeight:120, overflowY:"auto",
          border:"1px solid #334155",
        }}>
          {actionMsg}
        </pre>
      )}

      {/* Two-column: Models + Deployments */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16 }}>
        {/* Model versions */}
        <div>
          <h3 style={{ color:"#94a3b8", fontSize:13, marginBottom:8 }}>
            Model Registry ({models.length} versions)
          </h3>
          {loading ? (
            <div style={{ color:"#64748b" }}>Loading…</div>
          ) : models.length === 0 ? (
            <div style={{ color:"#475569", fontSize:12 }}>
              No models registered. Train a model and register it with MLflow.
            </div>
          ) : (
            <>
              {productionModels.map((m) => (
                <ModelVersionCard key={m.version} model={m} />
              ))}
              {stagingModels.map((m) => (
                <ModelVersionCard key={m.version} model={m} />
              ))}
              {archivedModels.slice(0,3).map((m) => (
                <ModelVersionCard key={m.version} model={m} />
              ))}
            </>
          )}
        </div>

        {/* Deployment history */}
        <div>
          <h3 style={{ color:"#94a3b8", fontSize:13, marginBottom:8 }}>
            Deployment History
          </h3>
          {deployments.map((d) => (
            <DeploymentRow key={d.id} dep={d} />
          ))}
          {deployments.length === 0 && (
            <div style={{ color:"#475569", fontSize:12 }}>
              No deployments yet.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}