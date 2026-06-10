"""Quick endpoint test — checks all major routes."""
import urllib.request
import urllib.error
import json
import sys

BASE = "http://localhost:8000"
API_KEY = "05ac3ecf4b9d6e8fc0a7f353d0d5023d83aa8b40bf4fb2ff277ab3f1eed5802a"
pass_count = 0
fail_count = 0
results = []

def req(method, path, body=None, expect_status=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Authorization": f"Bearer {API_KEY}"}
    if data:
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            status = resp.status
            try:
                resp_body = json.loads(resp.read())
            except:
                resp_body = "(binary/non-json)"
            return status, resp_body
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read())
        except:
            err_body = str(e)
        return e.code, err_body

def test(name, method, path, body=None, good_statuses=(200, 201, 204)):
    global pass_count, fail_count
    try:
        status, resp = req(method, path, body)
        ok = status in good_statuses
        mark = "PASS" if ok else "FAIL"
        if ok:
            pass_count += 1
        else:
            fail_count += 1
        results.append(f"[{mark}] {name} ({method} {path}) -> {status}")
        if not ok:
            resp_str = str(resp)[:120]
            results.append(f"       ERR: {resp_str}")
    except Exception as e:
        fail_count += 1
        results.append(f"[FAIL] {name} ({method} {path}) -> EXCEPTION: {e}")

# Health
test("Health check", "GET", "/health", good_statuses=(200, 503))
test("Demo status", "GET", "/demo/status")

# Demo data
test("Demo violations", "GET", "/demo/violations")
test("Demo dashboard", "GET", "/demo/dashboard")
test("Demo history", "GET", "/demo/history")

# Detections
test("List detections", "GET", "/detections?limit=5")
test("Detection stats", "GET", "/detections/stats")

# Sites
test("List sites", "GET", "/sites")
test("Create site", "POST", "/sites", {"site_id":"site-test","site_name":"Test Site","location":"Mumbai","country":"India","timezone":"Asia/Kolkata","industry_type":"manufacturing","contact_email":"test@site.com","active":True}, good_statuses=(201, 409))

# Cameras
test("Create camera", "POST", "/cameras", {"camera_id":"cam-test","camera_name":"Test Cam","rtsp_url":"rtsp://192.168.1.99/stream","location":"Test Area","zone_id":"zone-a","status":"active"}, good_statuses=(201, 409))
test("List cameras", "GET", "/cameras")

# Zones
test("List zones", "GET", "/zones")
import time as _time
test("Create zone", "POST", "/zones", {"zone_id":f"zone-ep-{int(_time.time())}","zone_name":"Test Zone","zone_type":"restricted","camera_id":"cam-001","polygon_norm":[{"x":0.1,"y":0.1},{"x":0.9,"y":0.1},{"x":0.9,"y":0.9},{"x":0.1,"y":0.9}],"required_ppe":["helmet"],"alert_enabled":True})

# Shifts
test("List shifts", "GET", "/shifts")
test("Active shifts", "GET", "/shifts/active")
test("Create shift", "POST", "/shifts", {"shift_name":"Test Shift","shift_type":"morning","start_time":"07:00","end_time":"15:00","site_id":"site-hq","active":True})

# Workers
test("List workers", "GET", "/workers")
test("Worker risk", "GET", "/workers/W001/risk")
test("Risk dashboard", "GET", "/workers/dashboard/risk")

# Alert config
test("List recipients", "GET", "/alert-config/recipients")
test("Alert stats", "GET", "/alert-config/stats")

# Proximity
test("List proximity", "GET", "/proximity-alerts")
test("Proximity stats", "GET", "/proximity-alerts/stats")

# Pose hazards
test("List pose hazards", "GET", "/pose-hazards")

# Fire
test("Fire status", "GET", "/fire/status")
test("Fire events", "GET", "/fire/events")

# Heatmap
test("Heatmap JSON", "GET", "/heatmap?format=json")

# Audit log
test("Audit log", "GET", "/audit?limit=5")

# Reports
test("List reports", "GET", "/reports")
test("Report stats", "GET", "/reports/stats/summary")

# Export
test("Export CSV", "GET", "/export/violations.csv")
test("Export JSON", "GET", "/export/violations.json")
test("Export workers CSV", "GET", "/export/workers.csv")

# MLOps
test("MLOps models", "GET", "/mlops/models")
test("MLOps deployments", "GET", "/mlops/deployments")
test("Canary status", "GET", "/mlops/canary/status")

# Agent
test("Agent status", "GET", "/agent/status")
test("Agent runs", "GET", "/agent/runs")

# Webhooks
test("List webhooks", "GET", "/webhooks")

# Print results
print("\n" + "="*60)
print(f"RESULTS: {pass_count} PASS / {fail_count} FAIL / {pass_count+fail_count} TOTAL")
print("="*60)
for r in results:
    print(r)
print(f"\nScore: {pass_count}/{pass_count+fail_count}")
