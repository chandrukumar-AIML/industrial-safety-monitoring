import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const NODE_CONFIG = {
  DetectViolation        : { icon: "🔍", color: "#6366f1" },
  CheckWorkerHistory     : { icon: "📋", color: "#0ea5e9" },
  ScoreSeverity          : { icon: "⚡", color: "#f59e0b" },
  DecideAlertLevel       : { icon: "🧠", color: "#8b5cf6" },
  GenerateIncidentReport : { icon: "📄", color: "#ec4899" },
  SendAlert              : { icon: "📱", color: "#ef4444" },
  LogToDatabase          : { icon: "💾", color: "#10b981" },
  UpdateComplianceScore  : { icon: "📊", color: "#06b6d4" },
};

const STATUS_COLOR = {
  COMPLETE            : "#22c55e",
  COMPLETE_WITH_ERRORS: "#ca8a04",
  FAILED              : "#dc2626",
  TIMEOUT             : "#ea580c",
  RUNNING             : "#6366f1",
  SKIPPED             : "#64748b",
};

function TraceStep({ step }) {
  const [open, setOpen] = useState(false);
  const cfg = NODE_CONFIG[step.node] || { icon: "•", color: "#64748b" };

  return (
    <div
      onClick={() => setOpen((v) => !v)}
      style={{
        background  : "#0f172a",
        border      : `1px solid ${cfg.color}33`,
        borderLeft  : `3px solid ${cfg.color}`,
        borderRadius: "0 8px 8px 0",
        padding     : "8px 12px",
        marginBottom: 4,
        cursor      : "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 16 }}>{cfg.icon}</span>
        <span style={{ color: cfg.color, fontWeight: 600, fontSize: 12 }}>
          {step.node}
        </span>
        <span style={{ color: "#475569", fontSize: 11, marginLeft: "auto" }}>
          {step.timestamp?.slice(11, 19)}
        </span>
        <span style={{ color: "#475569", fontSize: 12 }}>
          {open ? "▲" : "▼"}
        </span>
      </div>

      {open && step.details && (
        <div style={{
          marginTop  : 8,
          borderTop  : "1px solid #1e293b",
          paddingTop : 8,
        }}>
          {Object.entries(step.details).map(([k, v]) => (
            <div key={k} style={{
              display   : "flex",
              gap       : 8,
              fontSize  : 11,
              marginBottom: 2,
            }}>
              <span style={{ color: "#475569", minWidth: 140 }}>{k}:</span>
              <span style={{
                color     : typeof v === "boolean"
                  ? (v ? "#22c55e" : "#dc2626")
                  : "#94a3b8",
                fontFamily: "monospace",
              }}>
                {typeof v === "object"
                  ? JSON.stringify(v)
                  : String(v)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RunCard({ run, onSelect, selected }) {
  const statusColor = STATUS_COLOR[run.final_status] || "#64748b";
  const alertColor  = {
    CRITICAL: "#dc2626", HIGH: "#ea580c",
    MEDIUM: "#ca8a04", LOW: "#16a34a", NONE: "#64748b",
  }[run.alert_level] || "#64748b";

  return (
    <div
      onClick  = {() => onSelect(run.run_id)}
      style={{
        background  : selected ? "#1e3a5f" : "#1e293b",
        border      : `1px solid ${selected ? "#2563eb" : "#334155"}`,
        borderRadius: 10,
        padding     : "10px 14px",
        marginBottom: 6,
        cursor      : "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          color    : statusColor,
          fontSize : 11,
          fontWeight:700,
          minWidth : 70,
        }}>
          {run.final_status}
        </span>
        <span style={{ color: "#f1f5f9", fontWeight: 600, fontSize: 12 }}>
          {run.class_name}
        </span>
        <span style={{ color: "#64748b", fontSize: 11 }}>
          Track #{run.track_id}
        </span>
        <span style={{
          marginLeft  : "auto",
          color       : alertColor,
          fontSize    : 11,
          fontWeight  : 600,
        }}>
          {run.alert_level || "—"}
        </span>
      </div>
      <div style={{
        display: "flex", gap: 12,
        marginTop: 4, fontSize: 11, color: "#475569",
      }}>
        {run.severity_score && (
          <span>Severity: {run.severity_score}/10</span>
        )}
        {run.compliance_delta && (
          <span style={{ color: run.compliance_delta < 0 ? "#dc2626" : "#22c55e" }}>
            Compliance: {run.compliance_delta > 0 ? "+" : ""}{run.compliance_delta}
          </span>
        )}
        <span>{run.created_at?.slice(0, 16).replace("T", " ")}</span>
      </div>
    </div>
  );
}

export default function AgentTracePanel() {
  const [runs,       setRuns]       = useState([]);
  const [selected,   setSelected]   = useState(null);
  const [runDetail,  setRunDetail]  = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [status,     setStatus]     = useState(null);

  const fetchRuns = async () => {
    try {
      const [rRes, sRes] = await Promise.all([
        fetch(`${API_BASE}/agent/runs?limit=30`),
        fetch(`${API_BASE}/agent/status`),
      ]);
      setRuns(await rRes.json());
      setStatus(await sRes.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchDetail = async (runId) => {
    setSelected(runId);
    try {
      const res  = await fetch(`${API_BASE}/agent/runs/${runId}`);
      const data = await res.json();
      setRunDetail(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { fetchRuns(); }, []);
  useEffect(() => {
    const t = setInterval(fetchRuns, 15000);
    return () => clearInterval(t);
  }, []);

  const successCount  = runs.filter((r) => r.final_status === "COMPLETE").length;
  const failedCount   = runs.filter((r) => r.final_status === "FAILED").length;
  const criticalCount = runs.filter((r) => r.alert_level  === "CRITICAL").length;

  return (
    <div style={{ fontFamily: "system-ui", padding: "0 0 24px" }}>
      <h2 style={{ color: "#f1f5f9", fontSize: 18, marginBottom: 16 }}>
        Safety Agent Traces
      </h2>

      {/* Status */}
      {status && (
        <div style={{
          background  : "#1e293b",
          borderRadius: 10,
          padding     : "12px 16px",
          marginBottom: 16,
          display     : "flex",
          gap         : 16,
          alignItems  : "center",
          flexWrap    : "wrap",
          fontSize    : 12,
        }}>
          <div style={{
            width       : 8,
            height      : 8,
            borderRadius: "50%",
            background  : status.enabled ? "#22c55e" : "#dc2626",
          }} />
          <span style={{ color: "#94a3b8" }}>
            Model: <b style={{ color: "#f1f5f9" }}>{status.model}</b>
          </span>
          <span style={{ color: "#94a3b8" }}>
            LangSmith:{" "}
            <b style={{ color: status.langsmith_enabled ? "#22c55e" : "#64748b" }}>
              {status.langsmith_enabled ? "Active" : "Disabled"}
            </b>
          </span>
          <span style={{ color: "#94a3b8" }}>
            Max concurrent: <b style={{ color: "#f1f5f9" }}>{status.max_concurrent}</b>
          </span>
          <span style={{ color: "#94a3b8" }}>
            Severity threshold: <b style={{ color: "#f1f5f9" }}>{status.severity_threshold}/10</b>
          </span>
        </div>
      )}

      {/* Summary cards */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        {[
          { label: "Total Runs",  value: runs.length,    color: "#94a3b8" },
          { label: "Complete",    value: successCount,   color: "#22c55e" },
          { label: "Failed",      value: failedCount,    color: "#dc2626" },
          { label: "Critical",    value: criticalCount,  color: "#dc2626" },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            background  : "#1e293b",
            border      : "1px solid #334155",
            borderRadius: 10,
            padding     : "10px 16px",
            minWidth    : 100,
          }}>
            <div style={{ color, fontSize: 11, marginBottom: 2 }}>{label}</div>
            <div style={{ color: "#f1f5f9", fontSize: 22, fontWeight: 700 }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Split view */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Run list */}
        <div>
          <h3 style={{ color: "#94a3b8", fontSize: 13, marginBottom: 8 }}>
            Recent Runs
          </h3>
          {loading ? (
            <div style={{ color: "#64748b" }}>Loading...</div>
          ) : runs.length === 0 ? (
            <div style={{ color: "#475569", fontSize: 13 }}>
              No agent runs yet. Agent fires automatically on violations.
            </div>
          ) : (
            runs.map((r) => (
              <RunCard
                key      = {r.run_id}
                run      = {r}
                onSelect = {fetchDetail}
                selected = {selected === r.run_id}
              />
            ))
          )}
        </div>

        {/* Trace detail */}
        <div>
          <h3 style={{ color: "#94a3b8", fontSize: 13, marginBottom: 8 }}>
            {selected ? `Trace: ${selected}` : "Select a run to see trace"}
          </h3>
          {runDetail && (
            <>
              <div style={{
                background  : "#1e293b",
                borderRadius: 8,
                padding     : "10px 14px",
                marginBottom: 10,
                fontSize    : 12,
              }}>
                <div style={{ color: "#94a3b8", marginBottom: 4 }}>
                  Final state
                </div>
                {[
                  ["Status",     runDetail.final_status],
                  ["Alert Level",runDetail.alert_level || "—"],
                  ["Score",      runDetail.severity_score
                                   ? `${runDetail.severity_score}/10` : "—"],
                  ["Report",     runDetail.report_id || "—"],
                  ["Compliance Δ", runDetail.compliance_delta || "—"],
                ].map(([label, value]) => (
                  <div key={label} style={{
                    display: "flex", gap: 8, marginBottom: 2,
                  }}>
                    <span style={{ color: "#475569", minWidth: 100 }}>
                      {label}:
                    </span>
                    <span style={{ color: "#f1f5f9", fontWeight: 600 }}>
                      {String(value)}
                    </span>
                  </div>
                ))}
                {runDetail.error && (
                  <div style={{
                    marginTop   : 6,
                    color       : "#dc2626",
                    fontSize    : 11,
                    background  : "#7f1d1d",
                    borderRadius: 6,
                    padding     : "4px 8px",
                  }}>
                    Error: {runDetail.error}
                  </div>
                )}
              </div>

              <h4 style={{ color: "#64748b", fontSize: 12, marginBottom: 6 }}>
                Node trace ({runDetail.trace_steps?.length || 0} steps)
              </h4>
              {(runDetail.trace_steps || []).map((step, i) => (
                <TraceStep key={i} step={step} />
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}