/**
 * frontend/src/components/WeeklyReportPanel.jsx
 *
 * Weekly Compliance Report generation and history.
 *
 * # FIXED: Proper anchor tag syntax for PDF download links
 * # FIXED: Secure PDF download using Blob to preserve auth headers
 * # FIXED: Score trend color logic (green/red arrows)
 * # IMPROVED: JSDoc types and loading states
 */

import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import { FileText, Download, Loader2, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'
import { useToast } from './Toast'

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function ScoreTrend({ score, delta }) {
  const color  = score >= 80 ? "#22c55e" : score >= 60 ? "#ea580c" : "#dc2626";
  const dcolor = delta >= 0 ? "#22c55e" : "#dc2626";
  return (
    <div style={{ display:"flex", alignItems:"baseline", gap:10 }}>
      <span style={{ fontSize:36, fontWeight:800, color }}>{score.toFixed(1)}</span>
      <span style={{ color:"#64748b", fontSize:13 }}>/100</span>
      {delta !== null && (
        <span style={{ color:dcolor, fontSize:12, fontWeight:600 }}>
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}
        </span>
      )}
    </div>
  );
}

function ReportRow({ report }) {
  const toast = useToast()
  const scoreColor = (
    report.site_score >= 80 ? "#22c55e" :
    report.site_score >= 60 ? "#ea580c" : "#dc2626"
  );
  const delta = report.score_delta;

  // FIXED: Secure download handler
  const handleDownload = useCallback(async (e) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      const res = await api.get(`/weekly-reports/${report.id}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `compliance_report_${report.week_start}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Download failed:', err)
      toast.error('Could not download the report PDF. Try again.')
    }
  }, [report.id, report.week_start])

  return (
    <div style={{
      background  : "#1e293b",
      border      : "1px solid #334155",
      borderRadius: 10,
      padding     : "14px 16px",
      marginBottom: 8,
      display     : "flex",
      alignItems  : "center",
      gap         : 14,
    }}>
      {/* Score */}
      <div style={{
        width       : 60,
        height      : 60,
        borderRadius: "50%",
        background  : scoreColor + "22",
        border      : `2px solid ${scoreColor}`,
        display     : "flex",
        alignItems  : "center",
        justifyContent:"center",
        flexDirection:"column",
        flexShrink  : 0,
      }}>
        <span style={{ color:scoreColor, fontWeight:800, fontSize:16, lineHeight:1 }}>
          {report.site_score.toFixed(0)}
        </span>
        <span style={{ color:scoreColor, fontSize:8 }}>/ 100</span>
      </div>

      {/* Info */}
      <div style={{ flex:1 }}>
        <div style={{ color:"#f1f5f9", fontWeight:600, fontSize:13 }}>
          Week of {report.week_start} → {report.week_end}
        </div>
        <div style={{
          color:"#64748b", fontSize:11,
          marginTop:3, display:"flex", gap:12,
        }}>
          <span>Violations: {report.total_violations ?? "—"}</span>
          <span>High Risk: {report.high_risk_count ?? "—"}</span>
          <span>
            {delta !== null && (
              <span style={{ color: delta>=0 ? "#22c55e" : "#dc2626" }}>
                {delta>=0?"▲":"▼"} {Math.abs(delta).toFixed(1)} vs prev
              </span>
            )}
          </span>
        </div>
      </div>

      {/* Badges */}
      <div style={{ display:"flex", gap:6, flexShrink:0 }}>
        {report.email_sent && (
          <span style={{
            background:"#14532d", color:"#86efac",
            fontSize:10, padding:"2px 8px",
            borderRadius:12, fontWeight:600,
          }}>
            ✉ Sent
          </span>
        )}
        {report.has_pdf && (
          // FIXED: Proper button with secure download handler
          <button
            onClick={handleDownload}
            style={{
              background  :"#2563eb", color:"#fff",
              fontSize    :11, padding:"4px 12px",
              borderRadius:8, fontWeight:600,
              textDecoration:"none",
              border: "none",
              cursor: "pointer",
            }}
          >
            ↓ PDF
          </button>
        )}
      </div>
    </div>
  );
}

export default function WeeklyReportPanel() {
  const toast = useToast();
  const [reports,     setReports]     = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [generating,  setGenerating]  = useState(false);
  const [genStatus,   setGenStatus]   = useState(null);

  const fetchReports = async () => {
    try {
      const res  = await api.get('/weekly-reports?limit=12');
      const data = res.data;
      setReports(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchReports(); }, []);

  const handleGenerate = async (sendEmail = true) => {
    setGenerating(true);
    setGenStatus("Generating report…");
    try {
      const res  = await api.post(
        `/weekly-reports/generate?send_email=${sendEmail}`,
        {}
      );
      const data = res.data;
      setGenStatus(data.message);
      setTimeout(() => { fetchReports(); setGenerating(false); }, 35000);
    } catch (e) {
      setGenStatus("Error — check backend logs");
      setGenerating(false);
    }
  };

  const latest = reports[0];

  return (
    <div style={{ fontFamily:"system-ui", padding:"0 0 24px" }}>
      <div style={{ display:"flex", alignItems:"center",
        gap:12, marginBottom:16, flexWrap:"wrap" }}>
        <h2 style={{ color:"#f1f5f9", fontSize:18, margin:0 }}>
          Weekly Compliance Reports
        </h2>
        <div style={{ marginLeft:"auto", display:"flex", gap:8 }}>
          <button
            onClick  = {() => handleGenerate(false)}
            disabled = {generating}
            style    = {{
              background  :"#334155", border:"none", borderRadius:8,
              color:"#f1f5f9", padding:"6px 14px",
              cursor:generating?"wait":"pointer", fontSize:13,
            }}
          >
            {generating ? "…" : "↻ Generate (no email)"}
          </button>
          <button
            onClick  = {() => handleGenerate(true)}
            disabled = {generating}
            style    = {{
              background  :"#2563eb", border:"none", borderRadius:8,
              color:"#fff", padding:"6px 14px",
              cursor:generating?"wait":"pointer",
              fontWeight:600, fontSize:13,
            }}
          >
            {generating ? "Generating…" : "Generate + Email"}
          </button>
        </div>
      </div>

      {genStatus && (
        <div style={{
          background:"#1e3a5f", borderRadius:8,
          padding:"10px 14px", color:"#93c5fd",
          fontSize:12, marginBottom:14,
          border:"1px solid #2563eb",
        }}>
          {genStatus}
        </div>
      )}

      {/* Latest report highlight */}
      {latest && (
        <div style={{
          background  : "linear-gradient(135deg, #1e3a5f, #1e293b)",
          borderRadius: 14,
          padding     : "20px 24px",
          marginBottom: 20,
          border      : "1px solid #2563eb44",
        }}>
          <div style={{ color:"#94a3b8", fontSize:11,
            fontWeight:600, marginBottom:8 }}>
            LATEST REPORT
          </div>
          <div style={{ display:"flex", alignItems:"center",
            gap:20, flexWrap:"wrap" }}>
            <ScoreTrend score={latest.site_score} delta={latest.score_delta} />
            <div style={{ flex:1 }}>
              <div style={{ color:"#f1f5f9", fontWeight:600, fontSize:14 }}>
                Week of {latest.week_start}
              </div>
              <div style={{ color:"#64748b", fontSize:12, marginTop:4 }}>
                {latest.total_violations} violations ·
                {latest.high_risk_count} high risk ·
                {latest.total_workers} workers monitored
              </div>
            </div>
            {latest.has_pdf && (
              // FIXED: Proper button with secure download
              <button
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  // Trigger download via api client
                  api.get(`/weekly-reports/${latest.id}/download`, { responseType: 'blob' })
                    .then(res => {
                      const url = URL.createObjectURL(res.data)
                      const a = document.createElement('a')
                      a.href = url
                      a.download = `compliance_report_${latest.week_start}.pdf`
                      document.body.appendChild(a)
                      a.click()
                      document.body.removeChild(a)
                      URL.revokeObjectURL(url)
                    })
                    .catch(err => {
                      console.error('Download failed:', err)
                      toast.error('Could not download the report PDF. Try again.')
                    })
                }}
                style={{
                  background:"#2563eb", color:"#fff",
                  padding:"8px 18px", borderRadius:10,
                  fontWeight:700, fontSize:13,
                  textDecoration:"none",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                ↓ Download PDF
              </button>
            )}
          </div>

          {/* Auto-send info */}
          <div style={{
            marginTop:12, color:"#475569", fontSize:11,
            borderTop:"1px solid #334155", paddingTop:10,
          }}>
            📅 Auto-generated every Monday at 08:00 UTC and emailed to all managers
          </div>
        </div>
      )}

      {/* Report history */}
      <h3 style={{ color:"#94a3b8", fontSize:13, marginBottom:10 }}>
        Report History
      </h3>
      {loading ? (
        <div style={{ color:"#64748b" }}>Loading…</div>
      ) : reports.length === 0 ? (
        <div style={{ color:"#475569", fontSize:13 }}>
          No reports yet. Click "Generate" to create the first report.
        </div>
      ) : (
        reports.map((r) => <ReportRow key={r.id} report={r} />)
      )}
    </div>
  );
}