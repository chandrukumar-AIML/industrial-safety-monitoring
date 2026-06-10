# 🧪 Industrial Safety Monitor — Manual Testing Checklist

Use this after starting the full stack (`docker compose up -d` or backend + frontend manually).
Backend: `http://localhost:8000` | Frontend: `http://localhost:5173` | API Docs: `http://localhost:8000/docs`

---

## ✅ Pre-Flight

| # | Check | How | Expected |
|---|-------|-----|----------|
| 1 | Backend health | `curl http://localhost:8000/health` | `{"status":"ok","version":"..."}` |
| 2 | WebSocket stream | Open dashboard, check status bar | Green "Connected" badge, fps > 0 |
| 3 | Database connected | Check backend logs | `Database tables created` (no error) |
| 4 | Demo mode active | `curl http://localhost:8000/demo/full-dataset` | Returns synthetic violations, workers, etc. |
| 5 | API docs accessible | Open `http://localhost:8000/docs` | Swagger UI loads with all endpoints |

---

## 🧙 Onboarding Wizard

| # | Check | How | Expected |
|---|-------|-----|----------|
| 6 | First-time wizard shows | Clear `localStorage` key `sm_onboarding_done`, reload | 4-step wizard overlay appears |
| 7 | Step 1 — Welcome | Click "Enable Demo Mode" | Demo banner appears at top |
| 8 | Step 2 — Camera | Select "RTSP Stream", type `rtsp://192.168.1.100/stream` | URL saved in input |
| 9 | Step 3 — Alerts | Toggle "WhatsApp" + "Email" | Both checkboxes activate |
| 10 | Step 4 — Done | Click "Go to Dashboard" | Wizard dismisses, dashboard visible |
| 11 | Wizard stays dismissed | Reload page | Wizard does NOT reappear |

---

## 📊 Dashboard Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 12 | Stat cards render | Load dashboard | 4 cards: Violations Today, Active Tracks, FPS, Compliance % |
| 13 | Live feed | When backend running with camera | Video stream with bounding boxes |
| 14 | Heatmap panel | Load dashboard | Heatmap renders (blank if no data) |
| 15 | Analytics charts | Scroll down | Bar/line charts visible |
| 16 | Violation log | Scroll down | Table with columns: Time, Type, Zone, Severity, Camera |
| 17 | Pose hazard panel | Scroll to bottom | "Pose Hazards" panel with risk list |
| 18 | Proximity panel | Scroll to bottom | "Proximity Events" panel |

---

## 📷 Cameras Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 19 | Camera grid shows | Click Cameras nav | Grid with layout selector (1×1, 2×2, 3×3, 4×4) |
| 20 | Add camera (USB) | Click "+ Add Camera" in Camera Configuration → select "USB Cam 0" | Camera added to list with status badge |
| 21 | Add camera (RTSP) | Click "+ Add Camera" → select "RTSP Stream" → enter `rtsp://192.168.1.100/stream` → Save | Camera saved, appears in list |
| 22 | Camera status badge | After adding | Shows "connecting" → "active" or "error" |
| 23 | Delete camera | Click 🗑️ icon on camera row → confirm | Camera removed from list |
| 24 | Layout toggle | Click 3×3 button | Grid switches to 3-column layout |

---

## ⚠️ Violations Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 25 | Violations table | Load violations tab | Table with Time/Type/Zone/Severity/Camera columns |
| 26 | Filter by type | Click type dropdown → "No Helmet" | Table filters to helmet violations only |
| 27 | Filter by severity | Select "High" severity | Only high severity rows shown |
| 28 | Export CSV | Click "Export CSV" button | Browser downloads `violations.csv` |
| 29 | Export JSON | Click "Export JSON" button | Browser downloads `violations.json` |
| 30 | Agent trace panel | Scroll to bottom of Violations tab | LangGraph agent trace timeline visible |
| 31 | SHAP explanation | Click "Explain" on a violation row | SHAP modal opens with feature importance chart |

---

## 🔔 Alerts Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 32 | Alert config panel | Click Alerts nav | "Alert Configuration" with "+ Add Recipient" |
| 33 | Add email recipient | Click "+ Add Recipient" → Name: "Safety Manager", Role: Manager, Email: `test@example.com`, check Critical+High → Save | Recipient appears in "Active Recipients" list |
| 34 | Add WhatsApp recipient | Add recipient with WhatsApp: `+1234567890` | Saved with WhatsApp icon |
| 35 | Test alert | Click "Test" button on a recipient | "Sending…" spinner → success or error message |
| 36 | Delete recipient | Click trash icon → confirm | Recipient removed |
| 37 | Recent sends log | After a violation is detected | Log shows time/recipient/status (sent/failed/throttled) |

---

## 📄 Reports Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 38 | Weekly report | Click Reports nav | "Weekly Safety Report" section with date range |
| 39 | Generate report | Click "Generate Report" for this week | Report generates with violation counts, compliance %, recommendations |
| 40 | Report history | Scroll down | Past reports listed with date, download link |
| 41 | Download PDF | Click download icon on past report | PDF downloads |
| 42 | Export Reports CSV | Click "Export Reports" button | Downloads `reports.csv` |
| 43 | Export Workers CSV | Click "Export Workers" button | Downloads `workers.csv` |
| 44 | Export Zone Analytics | Click "Zone Analytics" button | Downloads `zone-analytics.csv` |

---

## 📈 Analytics Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 45 | Charts render | Click Analytics nav | Multiple charts: violations by type, by hour, by zone, trend over time |
| 46 | Time range | Select "Last 7 Days" | Charts update to show 7-day window |
| 47 | Zone filter | Select specific zone | Charts filter to that zone |

---

## 🤖 MLOps Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 48 | MLOps panel | Click MLOps nav | "MLOps — Model Registry & Canary Deploy" |
| 49 | Model registry | Load panel | Lists registered model versions (empty if none trained) |
| 50 | Start canary deploy | Click "Start Canary" → select model version → set traffic % | Canary deployment starts, shows traffic split |
| 51 | Canary traffic slider | Adjust slider 10%→50% | Traffic percentage updates |
| 52 | Promote canary | Click "Promote to Production" | Model becomes active version |
| 53 | Rollback | Click "Rollback" | Previous model restored |
| 54 | Drift detection | Panel shows drift metrics | Accuracy, data drift, concept drift gauges |

---

## 👥 Workers Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 55 | Worker profiles | Click Workers nav | "Worker Profiles" with search + "+ Enroll Worker" |
| 56 | Enroll worker | Click "+ Enroll Worker" → Name: "John Doe", ID: "W001", Department: "Floor A" → Save | Worker appears in list |
| 57 | Search worker | Type "John" in search | List filters to matching workers |
| 58 | Worker profile | Click on a worker card | Right panel shows compliance score, violations, shift info |
| 59 | Worker compliance | View profile | Shows PPE compliance %, violation history chart |

---

## 🗺️ Zones Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 60 | Zones view | Click Zones nav | Camera feed + Zone Drawer panel (on xl screens) |
| 61 | Zone drawer | Click 🗺️ button at sidebar bottom | Slide-over drawer appears on right |
| 62 | Add zone | Click "+ Add Zone" in drawer → draw rectangle on feed → name "Machine Bay" → Save | Zone outline appears on camera feed |
| 63 | Zone rules | Select zone → set "No Entry: Unauthorized" rule | Zone turns red when person detected |
| 64 | Delete zone | Click trash on zone entry | Zone removed from feed overlay |

---

## 🔗 Webhooks Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 65 | Webhooks panel | Click Webhooks nav | "Outbound Webhooks" with "+ Add Webhook" |
| 66 | Add Slack webhook | Click "+ Add Webhook" → Name: "Slack Alerts", URL: `https://hooks.slack.com/...`, Events: ["violation.critical"] → Save | Webhook appears in list |
| 67 | Add Teams webhook | Same process with Teams URL | Saved with Teams label |
| 68 | Test webhook | Click "Test" on webhook row | Sends test payload, shows 200 OK or error |
| 69 | Delete webhook | Click trash → confirm | Webhook removed |
| 70 | Event types | Open event type selector | Shows: violation.critical, violation.high, fire.detected, shift.start, report.generated |

---

## 📋 Audit Log Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 71 | Audit log panel | Click Audit Log nav | "Audit Log" with filter bar |
| 72 | Filter by action | Type "violation" in action filter → Apply | Shows only violation-related entries |
| 73 | Filter by actor | Type "system" in actor field → Apply | Shows system-generated entries |
| 74 | Date range filter | Set start: today-7, end: today → Apply | Shows last 7 days of audit entries |
| 75 | Clear filters | Click "Clear" | All entries reappear |
| 76 | Entry colors | View entries | Green=acknowledged, Red=deleted/revoked, Blue=created |
| 77 | Pagination | If >25 entries | Prev/Next buttons appear |

---

## ⚙️ Settings Tab

| # | Check | How | Expected |
|---|-------|-----|----------|
| 78 | Settings panel | Click Settings nav | Alert Configuration + Theme section |
| 79 | Dark mode toggle | Click ☀️/🌙 button | Page switches between dark/light theme |
| 80 | Dark mode persists | Toggle dark → reload | Theme preference remembered |

---

## 💬 Chat Panel (RAG Chatbot)

| # | Check | How | Expected |
|---|-------|-----|----------|
| 81 | Chat button | Click 💬 floating button | Chat panel slides up from bottom-right |
| 82 | Ask OSHA question | Type "What are OSHA requirements for hard hats?" → Send | AI responds with OSHA regulation text (cites source) |
| 83 | Ask violation question | Type "How many violations today?" → Send | AI responds with count from live data |
| 84 | Close chat | Click ✕ | Panel closes |

---

## 🔥 Fire Alert (Emergency)

| # | Check | How | Expected |
|---|-------|-----|----------|
| 85 | Fire detection | Trigger via demo: `POST /demo/trigger-fire` | Full-screen red overlay with "🔥 FIRE DETECTED — EVACUATE" |
| 86 | Fire overlay dismiss | Click "Acknowledge" | Overlay dismisses |
| 87 | Zone alert banner | Trigger zone violation | Yellow banner appears below status bar |

---

## 🔑 RBAC & API Keys (via API Docs at :8000/docs)

| # | Check | How | Expected |
|---|-------|-----|----------|
| 88 | Create API key | `POST /apikeys` with admin key in header: `{"name":"test-key","role":"operator"}` | Returns `{"key":"sm_...","id":1}` — save the key, shown once only |
| 89 | List API keys | `GET /apikeys` | Returns list with masked hashes |
| 90 | Operator access | Use operator key on `GET /violations` | Returns data |
| 91 | Operator blocked | Use operator key on `DELETE /apikeys/1` | Returns 403 Forbidden |
| 92 | Rotate key | `POST /apikeys/1/rotate` | Returns new key, old key deactivated |
| 93 | Delete key | `DELETE /apikeys/1` | Returns 204 No Content |

---

## 🏭 Multi-Site (via API Docs)

| # | Check | How | Expected |
|---|-------|-----|----------|
| 94 | Create site | `POST /sites`: `{"site_id":"plant-a","name":"Plant A","location":"Chennai"}` | `{"id":1,"site_id":"plant-a",...}` |
| 95 | List sites | `GET /sites` | Returns array of sites |
| 96 | Site summary | `GET /sites/1/summary` | Returns violation counts, compliance score, worker count for site |

---

## 📅 Shift Management (via API Docs)

| # | Check | How | Expected |
|---|-------|-----|----------|
| 97 | Create shift | `POST /shifts`: `{"name":"Morning","start_time":"06:00","end_time":"14:00","site_id":"plant-a"}` | Shift created |
| 98 | Get active shifts | `GET /shifts/active` | Returns currently active shifts based on UTC time |
| 99 | Assign worker | `POST /shifts/assign`: `{"shift_id":1,"worker_id":"W001"}` | 200 OK |
| 100 | Shift stats | `GET /shifts/1/stats` | Returns on_time, violations, compliance for that shift |

---

## 🤖 LLM Configuration Check

| # | Check | How | Expected |
|---|-------|-----|----------|
| 101 | Ollama primary | Check `.env`: `REPORT_LLM_PRIMARY=ollama` | Ollama used first for reports/chat |
| 102 | OpenAI fallback | Set `REPORT_LLM_PRIMARY=ollama`, `REPORT_LLM_FALLBACK=openai` | If Ollama fails, OpenAI used automatically |
| 103 | Weekly report LLM | Generate weekly report with Ollama running | Report text generated locally, no OpenAI cost |
| 104 | Agent LLM | Trigger incident (violation detected) | LangGraph agent uses Ollama for narrative, falls back to OpenAI |

---

## 🐳 Docker Smoke Test

```bash
# Start all services
docker compose up -d

# Verify all services healthy
docker compose ps

# Expected output:
# postgres   running  healthy
# backend    running  healthy (after ~30s)
# frontend   running
# mlflow     running
# redis      running (if configured)

# Check backend logs for startup
docker compose logs backend | grep -E "(started|error|Database)"

# Check pgAdmin accessible
open http://localhost:5050
# Login: admin@safety.local / pgadmin_password
```

---

## 🚀 Deploy Verification (Post-Deploy)

```bash
# Railway
railway status
railway logs

# VPS / DigitalOcean
docker compose -f docker-compose.yml ps
curl https://yourdomain.com/health

# Expected
# {"status":"ok","version":"1.0.0","db":"connected","demo_mode":false}
```

---

## Summary — Feature Coverage

| Category | Features | Status |
|----------|----------|--------|
| Detection | PPE, fire, pose, proximity | ✅ Backend done |
| AI | LangGraph agent, RAG chat, SHAP, drift | ✅ Done |
| Alerts | WhatsApp, Email, Webhooks, Fire overlay | ✅ Done |
| Data | PostgreSQL, CSV/JSON export, weekly PDF | ✅ Done |
| MLOps | Model registry, canary deploy, drift | ✅ Done |
| Enterprise | RBAC, API keys, multi-site, shifts, audit | ✅ Done |
| Frontend | All 12 tabs, dark mode, onboarding | ✅ Done |
| LLM | Ollama primary, OpenAI fallback | ✅ Config done |

---

*Built by Chandrukumar S — AI/ML Engineer | kumarchandru646@gmail.com*
