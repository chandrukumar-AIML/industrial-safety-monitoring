import { useState, useRef, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Message bubble ────────────────────────────────────────────
function MessageBubble({ msg }) {
  const isUser = msg.role === "user";

  return (
    <div
      style={{
        display       : "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom  : 12,
      }}
    >
      <div
        style={{
          maxWidth     : "75%",
          padding      : "10px 14px",
          borderRadius : isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background   : isUser ? "#2563eb" : "#1e293b",
          color        : "#f1f5f9",
          fontSize     : 14,
          lineHeight   : 1.55,
          whiteSpace   : "pre-wrap",
        }}
      >
        {msg.content}

        {/* Source citations */}
        {msg.sources && msg.sources.length > 0 && (
          <div style={{ marginTop: 10, borderTop: "1px solid #334155", paddingTop: 8 }}>
            <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 4 }}>
              Sources ({msg.sources.length})
            </div>
            {msg.sources.map((src, i) => (
              <div
                key={i}
                style={{
                  fontSize     : 11,
                  color        : "#64748b",
                  background   : "#0f172a",
                  borderRadius : 6,
                  padding      : "4px 8px",
                  marginBottom : 3,
                }}
              >
                <span style={{ color: "#38bdf8" }}>
                  [{i + 1}] {src.source}
                </span>
                {src.filename && ` · ${src.filename}`}
                {src.timestamp && ` · ${src.timestamp.slice(0, 16)}`}
                {src.zone_id && src.zone_id !== "none" && ` · Zone: ${src.zone_id}`}
                <div style={{ marginTop: 2, color: "#475569" }}>{src.excerpt}</div>
              </div>
            ))}
          </div>
        )}

        {/* Latency badge */}
        {msg.latency_ms && (
          <div style={{ marginTop: 6, fontSize: 10, color: "#475569" }}>
            {msg.latency_ms}ms · {msg.model_used} · {msg.retrieval_k} sources retrieved
          </div>
        )}
      </div>
    </div>
  );
}

// ── Typing indicator ──────────────────────────────────────────
function TypingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "8px 0" }}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            width        : 7,
            height       : 7,
            borderRadius : "50%",
            background   : "#64748b",
            animation    : `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
          40%            { transform: scale(1.2); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

// ── Sample queries ────────────────────────────────────────────
const SAMPLE_QUERIES = [
  "How many no-helmet violations occurred this week?",
  "Which zone had the most violations today?",
  "What does OSHA say about hard hat requirements?",
  "Show me the repeat offenders in zone-A",
  "What corrective actions should I take for glove violations?",
];

// ── Main ChatPanel component ──────────────────────────────────
export default function ChatPanel({ isOpen, onClose }) {
  const [messages, setMessages] = useState([
    {
      role   : "assistant",
      content: "Hi! I'm your safety compliance assistant. Ask me about PPE violations, OSHA regulations, or safety SOPs on your site.",
    },
  ]);
  const [input,    setInput]   = useState("");
  const [loading,  setLoading] = useState(false);
  const [error,    setError]   = useState(null);
  const bottomRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async (question) => {
    const q = (question || input).trim();
    if (!q || loading) return;

    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method  : "POST",
        headers : { "Content-Type": "application/json" },
        body    : JSON.stringify({ question: q, stream: false }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role      : "assistant",
          content   : data.answer,
          sources   : data.sources,
          latency_ms: data.latency_ms,
          model_used: data.model_used,
          retrieval_k: data.retrieval_k,
        },
      ]);
    } catch (err) {
      setError(err.message);
      setMessages((prev) => [
        ...prev,
        {
          role   : "assistant",
          content: `⚠️ Error: ${err.message}. Check that Ollama is running.`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position      : "fixed",
        bottom        : 24,
        right         : 24,
        width         : 420,
        height        : 600,
        background    : "#0f172a",
        border        : "1px solid #1e293b",
        borderRadius  : 16,
        display       : "flex",
        flexDirection : "column",
        boxShadow     : "0 25px 50px rgba(0,0,0,0.5)",
        zIndex        : 1000,
        fontFamily    : "system-ui, sans-serif",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding      : "14px 16px",
          borderBottom : "1px solid #1e293b",
          display      : "flex",
          alignItems   : "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width       : 8,
              height      : 8,
              borderRadius: "50%",
              background  : "#22c55e",
            }}
          />
          <span style={{ color: "#f1f5f9", fontWeight: 600, fontSize: 15 }}>
            Safety Assistant
          </span>
          <span style={{ color: "#64748b", fontSize: 11 }}>· Llama 3</span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border    : "none",
            color     : "#64748b",
            cursor    : "pointer",
            fontSize  : 18,
            padding   : 4,
          }}
        >
          ×
        </button>
      </div>

      {/* Messages */}
      <div
        style={{
          flex    : 1,
          overflowY: "auto",
          padding : "12px 14px",
        }}
      >
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {loading && <TypingIndicator />}
        {error && (
          <div style={{
            margin: "8px 0", padding: "8px 12px", borderRadius: 8,
            background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
            color: "#fca5a5", fontSize: 13,
          }}>
            ⚠ {error.includes("fetch") || error.includes("network")
                  ? "Couldn't reach the assistant. Check your connection and try again."
                  : error}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Sample queries */}
      {messages.length <= 1 && (
        <div style={{ padding: "0 14px 10px" }}>
          <div style={{ fontSize: 11, color: "#475569", marginBottom: 6 }}>
            Try asking:
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {SAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => sendMessage(q)}
                style={{
                  background  : "#1e293b",
                  border      : "1px solid #334155",
                  borderRadius: 12,
                  color       : "#94a3b8",
                  fontSize    : 11,
                  padding     : "4px 10px",
                  cursor      : "pointer",
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div
        style={{
          padding    : "10px 12px",
          borderTop  : "1px solid #1e293b",
          display    : "flex",
          gap        : 8,
          alignItems : "flex-end",
        }}
      >
        <textarea
          value       = {input}
          onChange    = {(e) => setInput(e.target.value)}
          onKeyDown   = {handleKeyDown}
          placeholder = "Ask about violations, OSHA rules, SOPs..."
          rows        = {1}
          style={{
            flex        : 1,
            background  : "#1e293b",
            border      : "1px solid #334155",
            borderRadius: 10,
            color       : "#f1f5f9",
            fontSize    : 13,
            padding     : "8px 12px",
            resize      : "none",
            outline     : "none",
            lineHeight  : 1.4,
          }}
        />
        <button
          onClick   = {() => sendMessage()}
          disabled  = {loading || !input.trim()}
          style={{
            background  : loading || !input.trim() ? "#1e293b" : "#2563eb",
            border      : "none",
            borderRadius: 10,
            color       : "#f1f5f9",
            cursor      : loading || !input.trim() ? "not-allowed" : "pointer",
            padding     : "8px 14px",
            fontSize    : 14,
            fontWeight  : 600,
          }}
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}