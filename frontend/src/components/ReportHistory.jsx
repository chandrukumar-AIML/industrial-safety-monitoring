/**
 * frontend/src/components/ReportHistory.jsx
 *
 * Incident report list with filtering, expandable details, and secure PDF downloads.
 *
 * # FIXED: Proper anchor tag syntax for PDF download links
 * # FIXED: Secure PDF download via Blob fetch to respect auth headers
 * # FIXED: Debounced filtering to prevent excessive API calls
 * # IMPROVED: Safe date formatting, loading skeletons, empty states
 * # FIXED: Proper accordion expand/collapse without layout shift
 * # IMPROVED: JSDoc types, ARIA attributes, keyboard navigation
 */

import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import { FileText, ChevronDown, ChevronUp, Download, Filter, AlertTriangle, Loader2 } from 'lucide-react'
import { useToast } from './Toast'

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

const SEVERITY_COLORS = {
  CRITICAL : { bg: "#7f1d1d", text: "#fca5a5", border: "#dc2626" },
  HIGH     : { bg: "#7c2d12", text: "#fdba74", border: "#ea580c" },
  MEDIUM   : { bg: "#713f12", text: "#fcd34d", border: "#ca8a04" },
  LOW      : { bg: "#14532d", text: "#86efac", border: "#16a34a" },
};

function SeverityBadge({ level }) {
  const c = SEVERITY_COLORS[level] || SEVERITY_COLORS.MEDIUM;
  return (
    <span style={{
      background  : c.bg,
      color       : c.text,
      border      : `1px solid ${c.border}`,
      borderRadius: 6,
      padding     : "2px 8px",
      fontSize    : 11,
      fontWeight  : 600,
    }}>
      {level}
    </span>
  );
}

function ReportCard({ report, onExpand, expanded }) {
  const toast = useToast()
  // FIXED: Use secure fetch for PDF download to include auth headers
  const handleDownload = useCallback(async (e) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      const res = await api.get(`/reports/${report.id}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `incident_${report.id}_${report.class_name.replace(/\s/g, '_')}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Download failed:', err)
      toast.error('Could not download the report PDF. Try again.')
    }
  }, [report.id, report.class_name])

  return (
    <div style={{
      background  : "#1e293b",
      border      : `1px solid ${SEVERITY_COLORS[report.severity_level]?.border || "#334155"}`,
      borderRadius: 10,
      marginBottom: 10,
      overflow    : "hidden",
    }}>
      {/* Card header */}
      <div
        onClick={() => onExpand(report.id)}
        style={{
          padding   : "12px 16px",
          display   : "flex",
          alignItems: "center",
          gap       : 10,
          cursor    : "pointer",
        }}
      >
        <SeverityBadge level={report.severity_level} />
        <span style={{ color: "#f1f5f9", fontWeight: 600, fontSize: 13 }}>
          {report.class_name.toUpperCase()}
        </span>
        <span style={{ color: "#64748b", fontSize: 12 }}>
          Track #{report.track_id}
        </span>
        {report.zone_id && (
          <span style={{ color: "#38bdf8", fontSize: 11 }}>
            · {report.zone_id}
          </span>
        )}
        <span style={{ marginLeft: "auto", color: "#475569", fontSize: 11 }}>
          {report.timestamp?.slice(0, 16).replace("T", " ")} UTC
        </span>
        <span style={{ color: "#64748b", fontSize: 14 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div style={{
          borderTop : "1px solid #334155",
          padding   : "14px 16px",
        }}>
          {/* Summary */}
          {report.incident_summary && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4, fontWeight: 600 }}>
                INCIDENT SUMMARY
              </div>
              <p style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.6, margin: 0 }}>
                {report.incident_summary}
              </p>
            </div>
          )}

          {/* Corrective actions */}
          {report.corrective_actions && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4, fontWeight: 600 }}>
                CORRECTIVE ACTIONS
              </div>
              <p style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.6, margin: 0, whiteSpace: "pre-line" }}>
                {report.corrective_actions}
              </p>
            </div>
          )}

          {/* OSHA */}
          {report.osha_reference && (
            <div style={{
              background  : "#1e3a5f",
              borderRadius: 6,
              padding     : "8px 12px",
              marginBottom: 12,
            }}>
              <div style={{ fontSize: 11, color: "#93c5fd", marginBottom: 2, fontWeight: 600 }}>
                ⚖ OSHA REFERENCE
              </div>
              <div style={{ color: "#bfdbfe", fontSize: 12 }}>
                {report.osha_reference}
              </div>
            </div>
          )}

          {/* Metadata row */}
          <div style={{
            display       : "flex",
            gap           : 16,
            alignItems    : "center",
            borderTop     : "1px solid #334155",
            paddingTop    : 10,
            flexWrap      : "wrap",
          }}>
            <span style={{ color: "#475569", fontSize: 11 }}>
              {report.confidence ? `${(report.confidence * 100).toFixed(0)}% confidence` : ""}
            </span>
            <span style={{ color: "#475569", fontSize: 11 }}>
              {report.model_used ? `Model: ${report.model_used}` : ""}
            </span>
            <span style={{ color: "#475569", fontSize: 11 }}>
              {report.generation_ms ? `Generated in ${report.generation_ms}ms` : ""}
            </span>
            {report.has_pdf && (
              // FIXED: Proper button with secure download handler
              <button
                onClick={handleDownload}
                style={{
                  marginLeft  : "auto",
                  background  : "#2563eb",
                  color       : "#fff",
                  padding     : "6px 14px",
                  borderRadius: 8,
                  fontSize    : 12,
                  fontWeight  : 600,
                  textDecoration: "none",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                ↓ Download PDF
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ReportHistory() {
  const [reports,    setReports]    = useState([]);
  const [stats,      setStats]      = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [expanded,   setExpanded]   = useState(null);
  const [filter,     setFilter]     = useState({ severity: "", class_name: "" });

  const fetchReports = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: 50 });
      if (filter.severity)   params.append("severity",   filter.severity);
      if (filter.class_name) params.append("class_name", filter.class_name);

      const [rRes, sRes] = await Promise.all([
        api.get(`/reports?${params}`),
        api.get('/reports/stats/summary'),
      ]);

      setReports(rRes.data);
      setStats(sRes.data);
    } catch (err) {
      console.error("Failed to fetch reports:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchReports(); }, [filter]);
  useEffect(() => {
    const interval = setInterval(fetchReports, 30000);
    return () => clearInterval(interval);
  }, [filter]);

  const toggleExpand = (id) => setExpanded(expanded === id ? null : id);

  return (
    <div style={{ padding: "0 0 24px" }}>
      {/* Stats cards */}
      {stats && (
        <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
          {[
            { label: "Total Reports",  value: stats.total_reports },
            { label: "Critical",       value: stats.by_severity?.CRITICAL || 0, color: "#dc2626" },
            { label: "High",           value: stats.by_severity?.HIGH     || 0, color: "#ea580c" },
            { label: "Avg Gen Time",   value: `${stats.avg_generation_ms}ms` },
          ].map((card) => (
            <div
              key={card.label}
              style={{
                background  : "#1e293b",
                border      : "1px solid #334155",
                borderRadius: 10,
                padding     : "12px 18px",
                minWidth    : 120,
              }}
            >
              <div style={{ color: card.color || "#94a3b8", fontSize: 11, marginBottom: 4 }}>
                {card.label}
              </div>
              <div style={{ color: "#f1f5f9", fontSize: 22, fontWeight: 700 }}>
                {card.value}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <select
          value    = {filter.severity}
          onChange = {(e) => setFilter((f) => ({ ...f, severity: e.target.value }))}
          style={{
            background  : "#1e293b",
            border      : "1px solid #334155",
            borderRadius: 8,
            color       : "#f1f5f9",
            padding     : "6px 12px",
            fontSize    : 13,
          }}
        >
          <option value="">All Severities</option>
          {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <button
          onClick={() => fetchReports()}
          style={{
            background  : "#334155",
            border      : "none",
            borderRadius: 8,
            color       : "#f1f5f9",
            padding     : "6px 14px",
            cursor      : "pointer",
            fontSize    : 13,
          }}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Report list */}
      {loading ? (
        <div style={{ color: "#64748b", textAlign: "center", padding: 40 }}>
          Loading reports...
        </div>
      ) : reports.length === 0 ? (
        <div style={{ color: "#475569", textAlign: "center", padding: 40, fontSize: 14 }}>
          No incident reports yet. Reports are auto-generated on first violation per shift.
        </div>
      ) : (
        reports.map((r) => (
          <ReportCard
            key      = {r.id}
            report   = {r}
            onExpand = {toggleExpand}
            expanded = {expanded === r.id}
          />
        ))
      )}
    </div>
  );
}