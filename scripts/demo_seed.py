"""
scripts/demo_seed.py
====================
Full demo data seeder — Industrial Safety Monitor.
Seeds ALL tables with realistic mock data for demo/portfolio.

Usage:
    python scripts/demo_seed.py           # seed (skip existing)
    python scripts/demo_seed.py --reset   # wipe + re-seed
    python scripts/demo_seed.py --check   # verify table counts only
"""

import asyncio, argparse, json, random, sys, os, hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from backend.database import AsyncSessionLocal, init_db
from sqlalchemy import text

UTC = timezone.utc
def now():    return datetime.now(UTC)
def ago(**kw):return now() - timedelta(**kw)
def fmt(dt):  return dt.strftime("%Y-%m-%d %Human:%M:%S") if dt else None
def fmti(dt): return dt.isoformat() if dt else None

VIOLATION_CLASSES = ["no hardhat","no vest","no gloves","no boots","no goggles","no mask","no harness"]
SEVERITIES        = ["LOW","MEDIUM","HIGH","CRITICAL"]
WORK_TYPES        = ["hot_work","confined_space","electrical","height_work","chemical","excavation","radiation","cold_work","general"]

def rnd_conf():  return round(random.uniform(0.72, 0.99), 3)
def rnd_bbox():  return (random.randint(50,300),random.randint(50,200),random.randint(320,700),random.randint(220,550))

# ─────────────────────────────────────────────────────────────────────────────
# SITE & ZONE
# ─────────────────────────────────────────────────────────────────────────────
async def seed_sites(sess):
    print("  -> sites...")
    rows = [
        ("site-hq",     "HQ Plant",          "Chennai, Tamil Nadu",   "India","Asia/Kolkata","construction"),
        ("site-north",  "North Facility",     "Delhi NCR",             "India","Asia/Kolkata","warehouse"),
        ("site-east",   "East Steel Works",   "Jamshedpur, Jharkhand", "India","Asia/Kolkata","steel_manufacturing"),
        ("site-west",   "West Refinery",      "Jamnagar, Gujarat",     "India","Asia/Kolkata","oil_gas"),
        ("site-pharma", "Pharma Unit 3",      "Hyderabad, Telangana",  "India","Asia/Kolkata","pharma"),
        ("site-power",  "NTPC Unit 2",        "Singrauli, MP",         "India","Asia/Kolkata","power_plant"),
    ]
    for sid,name,loc,country,tz,ind in rows:
        await sess.execute(text("""
            INSERT INTO sites (site_id,site_name,location,country,timezone,industry_type,active)
            VALUES (:sid,:name,:loc,:c,:tz,:ind,1)
            ON CONFLICT(site_id) DO NOTHING
        """), dict(sid=sid,name=name,loc=loc,c=country,tz=tz,ind=ind))
    print(f"    OK {len(rows)} sites")

async def seed_zones(sess):
    print("  -> zones (camera_zones)...")
    rows = [
        ("zone-main-gate",  "Main Gate",        "entry",     "cam-001","site-hq",  '["no hardhat","no vest"]'),
        ("zone-floor-1",    "Production Floor", "restricted","cam-002","site-hq",  '["no hardhat","no vest","no gloves"]'),
        ("zone-welding",    "Welding Bay",      "hazardous", "cam-003","site-hq",  '["no hardhat","no vest","no goggles","no gloves"]'),
        ("zone-chemical",   "Chemical Store",   "hazardous", "cam-004","site-hq",  '["no hardhat","no vest","no mask","no gloves"]'),
        ("zone-warehouse",  "Warehouse Floor",  "general",   "cam-005","site-north",'["no vest"]'),
        ("zone-boiler",     "Boiler Room",      "critical",  "cam-006","site-power",'["no hardhat","no vest","no boots","no goggles"]'),
        ("zone-crane",      "Crane Area",       "hazardous", "cam-007","site-east", '["no hardhat","no harness","no vest"]'),
        ("zone-loading",    "Loading Dock",     "general",   "cam-008","site-west", '["no vest","no boots"]'),
        ("zone-lab",        "QC Laboratory",    "restricted","cam-009","site-pharma",'["no mask","no gloves","no goggles"]'),
        ("zone-control",    "Control Room",     "general",   "cam-010","site-power",'["no hardhat"]'),
    ]
    for zid,zname,ztype,cam,site,ppe in rows:
        await sess.execute(text("""
            INSERT INTO camera_zones
                (zone_id,zone_name,zone_type,camera_id,required_ppe,alert_enabled,active)
            VALUES (:zid,:zname,:ztype,:cam,:ppe,1,1)
            ON CONFLICT(zone_id) DO NOTHING
        """), dict(zid=zid,zname=zname,ztype=ztype,cam=cam,ppe=ppe))
    print(f"    OK {len(rows)} zones")

async def seed_cameras(sess):
    print("  -> cameras...")
    rows = [
        ("cam-001","Main Gate Camera",    "rtsp://192.168.1.10/stream1","zone-main-gate","active"),
        ("cam-002","Production Floor A",  "rtsp://192.168.1.11/stream1","zone-floor-1",  "active"),
        ("cam-003","Welding Bay",         "rtsp://192.168.1.12/stream1","zone-welding",  "active"),
        ("cam-004","Chemical Store",      "rtsp://192.168.1.13/stream1","zone-chemical", "active"),
        ("cam-005","Warehouse Floor",     "rtsp://192.168.1.14/stream1","zone-warehouse","active"),
        ("cam-006","Boiler Room",         "rtsp://192.168.1.15/stream1","zone-boiler",   "active"),
        ("cam-007","Crane Zone",          "rtsp://192.168.1.16/stream1","zone-crane",    "active"),
        ("cam-008","Loading Dock",        "rtsp://192.168.1.17/stream1","zone-loading",  "active"),
        ("cam-009","QC Lab",              "rtsp://192.168.1.18/stream1","zone-lab",      "degraded"),
        ("cam-010","Control Room",        "rtsp://192.168.1.19/stream1","zone-control",  "active"),
    ]
    for cid,cname,rtsp,zone,status in rows:
        await sess.execute(text("""
            INSERT INTO camera_registry
                (camera_id,camera_name,rtsp_url,location,zone_id,status)
            VALUES (:cid,:cname,:rtsp,:cname,:zone,:status)
            ON CONFLICT(camera_id) DO NOTHING
        """), dict(cid=cid,cname=cname,rtsp=rtsp,zone=zone,status=status))
    print(f"    OK {len(rows)} cameras")

# ─────────────────────────────────────────────────────────────────────────────
# WORKERS
# ─────────────────────────────────────────────────────────────────────────────
async def seed_workers(sess):
    print("  -> workers...")
    rows = [
        ("W001","Ravi Kumar",     "Welding",      "morning",   "operator",  "site-hq",    8.5,"HIGH"),
        ("W002","Suresh Raj",     "Fabrication",  "morning",   "operator",  "site-hq",    5.0,"MEDIUM"),
        ("W003","Priya Devi",     "QC",           "morning",   "supervisor","site-pharma",2.0,"LOW"),
        ("W004","Arun Sharma",    "Electrical",   "night",     "operator",  "site-hq",   15.0,"HIGH"),
        ("W005","Kiran Babu",     "Crane Ops",    "morning",   "operator",  "site-east",  3.5,"LOW"),
        ("W006","Deepa Nair",     "Safety",       "morning",   "safety_off","site-hq",    0.0,"LOW"),
        ("W007","Mohammed Rafi",  "Chemical",     "morning",   "operator",  "site-west", 18.0,"CRITICAL"),
        ("W008","Lakshmi Iyer",   "Production",   "afternoon", "operator",  "site-hq",    6.0,"MEDIUM"),
        ("W009","Vijay Anand",    "Maintenance",  "morning",   "operator",  "site-power", 9.0,"MEDIUM"),
        ("W010","Saranya Mani",   "Boiler Ops",   "morning",   "operator",  "site-power", 7.0,"MEDIUM"),
        ("W011","Rajesh Pillai",  "Loading",      "morning",   "operator",  "site-west",  4.0,"LOW"),
        ("W012","Anitha Gopal",   "Lab Tech",     "morning",   "operator",  "site-pharma",1.0,"LOW"),
        ("W013","Selvan Kumar",   "Welding",      "night",     "operator",  "site-hq",   12.0,"HIGH"),
        ("W014","Meena Sundaram", "Control Room", "morning",   "operator",  "site-power", 2.0,"LOW"),
        ("W015","Karthi Vel",     "Security",     "morning",   "guard",     "site-hq",    0.5,"LOW"),
    ]
    for wid,name,dept,shift,role,site,risk,rlevel in rows:
        await sess.execute(text("""
            INSERT INTO worker_profiles
                (worker_id,full_name,department,shift,role,risk_score,risk_level,active)
            VALUES (:wid,:name,:dept,:shift,:role,:risk,:rlevel,1)
            ON CONFLICT(worker_id) DO NOTHING
        """), dict(wid=wid,name=name,dept=dept,shift=shift,role=role,risk=risk,rlevel=rlevel))
    print(f"    OK {len(rows)} workers")

async def seed_shifts(sess):
    print("  -> shifts...")
    rows = [
        ("Morning Shift",  "fixed","06:00","14:00","site-hq",  "Ravi Supervisor",30),
        ("Afternoon Shift","fixed","14:00","22:00","site-hq",  "Murugan Sup",    25),
        ("Night Shift",    "fixed","22:00","06:00","site-hq",  "Anbu Sup",       20),
        ("General Shift",  "fixed","08:00","17:00","site-pharma","Dr. Priya",    15),
        ("Power Shift A",  "fixed","06:00","14:00","site-power","Vijay Sup",     20),
    ]
    # Only insert if shifts table is mostly empty
    r = await sess.execute(text("SELECT COUNT(*) FROM shifts"))
    if r.scalar() < 3:
        for sname,stype,start,end,site,sup,maxw in rows:
            await sess.execute(text("""
                INSERT INTO shifts (shift_name,shift_type,start_time,end_time,site_id,supervisor_name,max_workers,active)
                VALUES (:sname,:stype,:start,:end,:site,:sup,:maxw,1)
            """), dict(sname=sname,stype=stype,start=start,end=end,site=site,sup=sup,maxw=maxw))
        print(f"    OK {len(rows)} shifts inserted")
    else:
        print("    OK shifts already seeded")

# ─────────────────────────────────────────────────────────────────────────────
# DETECTIONS  (90-day history)
# ─────────────────────────────────────────────────────────────────────────────
async def seed_violations(sess):
    print("  -> violations (90-day history)...")
    zones   = ["zone-main-gate","zone-floor-1","zone-welding","zone-chemical","zone-warehouse","zone-boiler","zone-crane"]
    cams    = ["cam-001","cam-002","cam-003","cam-004","cam-005","cam-006","cam-007"]
    workers = ["W001","W002","W003","W004","W005","W007","W008","W009","W010","W013"]
    count   = 0
    track   = 100

    for day in range(90, 0, -1):
        d = ago(days=day)
        n = random.randint(0, 8)
        for _ in range(n):
            ts = d.replace(hour=random.randint(6,18),
                           minute=random.randint(0,59),
                           second=random.randint(0,59),
                           microsecond=0)
            x1,y1,x2,y2 = rnd_bbox()
            sev = random.choices(SEVERITIES, weights=[30,40,20,10])[0]
            ack = random.random() > 0.35
            zi  = random.randint(0, len(zones)-1)
            await sess.execute(text("""
                INSERT INTO violation_events
                    (track_id,class_name,confidence,zone_id,camera_id,site_id,
                     bbox_x1,bbox_y1,bbox_x2,bbox_y2,frame_idx,
                     severity_level,acknowledged,timestamp)
                VALUES
                    (:tid,:cls,:conf,:zone,:cam,:site,
                     :x1,:y1,:x2,:y2,:fidx,
                     :sev,:ack,:ts)
            """), dict(
                tid=track, cls=random.choice(VIOLATION_CLASSES), conf=rnd_conf(),
                zone=zones[zi], cam=cams[zi % len(cams)], site="site-hq",
                x1=x1,y1=y1,x2=x2,y2=y2,
                fidx=random.randint(1,9999),
                sev=sev, ack=1 if ack else 0,
                ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
            ))
            track += 1
            count += 1
    print(f"    OK {count} violations")

# ─────────────────────────────────────────────────────────────────────────────
# FIRE, PROXIMITY, POSE
# ─────────────────────────────────────────────────────────────────────────────
async def seed_fire_events(sess):
    print("  -> fire/smoke events...")
    for i in range(8):
        ts = ago(hours=random.randint(2, 200))
        x1,y1,x2,y2 = rnd_bbox()
        htype = random.choice(["fire","smoke","fire"])
        await sess.execute(text("""
            INSERT INTO fire_hazard_events
                (camera_id,zone_id,confidence,bbox_x1,bbox_y1,bbox_x2,bbox_y2,
                 hazard_type,acknowledged,timestamp)
            VALUES (:cam,:zone,:conf,:x1,:y1,:x2,:y2,:htype,:ack,:ts)
        """), dict(
            cam=random.choice(["cam-003","cam-006","cam-004"]),
            zone=random.choice(["zone-welding","zone-boiler","zone-chemical"]),
            conf=rnd_conf(), x1=x1,y1=y1,x2=x2,y2=y2,
            htype=htype, ack=1 if i < 6 else 0,
            ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    print("    OK 8 fire events")

async def seed_proximity_alerts(sess):
    print("  -> proximity alerts...")
    for i in range(12):
        ts = ago(hours=random.randint(1, 168))
        await sess.execute(text("""
            INSERT INTO proximity_alerts
                (person_track_id,machine_track_id,machine_class,
                 pixel_distance,real_distance_m,alert_level,
                 zone_id,camera_id,acknowledged,timestamp)
            VALUES (:ptid,:mtid,:mclass,:pdist,:rdist,:level,:zone,:cam,:ack,:ts)
        """), dict(
            ptid=random.randint(200,300), mtid=random.randint(400,500),
            mclass=random.choice(["forklift","crane","conveyor","excavator"]),
            pdist=random.randint(30,120),
            rdist=round(random.uniform(0.5, 4.5), 2),
            level=random.choice(["WARNING","CRITICAL","WARNING"]),
            zone=random.choice(["zone-warehouse","zone-crane","zone-floor-1"]),
            cam=random.choice(["cam-005","cam-007","cam-002"]),
            ack=1 if i < 9 else 0,
            ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    print("    OK 12 proximity alerts")

async def seed_pose_hazards(sess):
    print("  -> pose hazard events...")
    htypes = ["slouching","restricted_zone_entry","fall_detected","fatigue_posture","unsafe_reach"]
    for i in range(10):
        ts = ago(hours=random.randint(1, 120))
        await sess.execute(text("""
            INSERT INTO pose_hazard_events
                (track_id,hazard_type,severity,zone_id,camera_id,
                 duration_s,confidence,timestamp)
            VALUES (:tid,:htype,:sev,:zone,:cam,:dur,:conf,:ts)
        """), dict(
            tid=random.randint(500,600),
            htype=random.choice(htypes),
            sev=random.choice(["LOW","MEDIUM","HIGH"]),
            zone=random.choice(["zone-floor-1","zone-welding","zone-boiler"]),
            cam=random.choice(["cam-002","cam-003","cam-006"]),
            dur=round(random.uniform(2.0, 30.0), 1),
            conf=rnd_conf(),
            ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    print("    OK 10 pose hazard events")

# ─────────────────────────────────────────────────────────────────────────────
# INCIDENT REPORTS
# ─────────────────────────────────────────────────────────────────────────────
async def seed_reports(sess):
    print("  -> incident reports...")
    workers = ["W001","W002","W004","W007","W009","W013"]
    zones   = ["zone-welding","zone-chemical","zone-boiler","zone-floor-1"]
    cams    = ["cam-003","cam-004","cam-006","cam-002"]
    for i in range(15):
        ts    = ago(days=random.randint(1,60))
        vcls  = random.choice(VIOLATION_CLASSES)
        sev   = random.choice(SEVERITIES)
        rid   = f"RPT-{ts.strftime('%Y%m%d')}-{i:04d}"
        await sess.execute(text("""
            INSERT OR IGNORE INTO incident_reports
                (violation_id,track_id,class_name,zone_id,confidence,
                 incident_summary,root_cause_analysis,corrective_actions,
                 narrative,osha_reference,severity_level,severity,
                 model_used,status,created_at)
            VALUES
                (:vid,:tid,:cls,:zone,:conf,
                 :summary,:rca,:actions,
                 :narrative,:osha,:sev_level,:sev,
                 :model,:status,:ts)
        """), dict(
            vid=None, tid=100+i, cls=vcls,
            zone=random.choice(zones), conf=rnd_conf(),
            summary=f"Worker detected without {vcls.replace('no ','')} in {random.choice(zones).replace('zone-','')} area. Immediate action taken.",
            rca=f"Root cause: Inadequate PPE enforcement at zone entry. Worker bypassed checkpoint without proper gear inspection.",
            actions=f"1. Zone entry blocked until PPE complied.\n2. Supervisor notified within 2 minutes.\n3. Worker issued fresh PPE and re-briefed.",
            narrative=f"On {ts.strftime('%d %b %Y at %H:%M')}, Camera {random.choice(cams)} detected worker {random.choice(workers)} in {random.choice(zones).replace('zone-','')} zone without mandatory {vcls.replace('no ','')}. AI confidence: {rnd_conf():.0%}. Escalation L1 triggered. Supervisor {random.choice(['Ravi','Murugan','Deepa'])} acknowledged in {random.randint(3,15)} minutes.",
            osha=random.choice(["OSHA 1926.100","OSHA 1910.132","IS 4770","IS 15748","IS 818"]),
            sev_level=sev, sev=sev,
            model=random.choice(["groq","template","ollama"]),
            status=random.choice(["completed","completed","completed","pending"]),
            ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    print("    OK 15 incident reports")

# ─────────────────────────────────────────────────────────────────────────────
# ALERT RECIPIENTS
# ─────────────────────────────────────────────────────────────────────────────
async def seed_alert_recipients(sess):
    print("  -> alert recipients...")
    rows = [
        ("Safety Officer Deepa", "safety_officer","deepa@example.com","+919876543210",1,1,1,1),
        ("Plant Head Ramesh",    "plant_head",    "ramesh@example.com","+919876543211",0,0,1,1),
        ("HR Manager Anitha",    "hr_manager",    "anitha@example.com","+919876543212",0,1,1,1),
        ("Supervisor Murugan",   "supervisor",    "murugan@example.com","+919876543213",1,1,1,1),
    ]
    for name,role,email,wa,crit,high,med,low in rows:
        await sess.execute(text("""
            INSERT INTO alert_recipients
                (name,role,email,whatsapp_number,notify_critical,notify_high,notify_medium,notify_low,active)
            VALUES (:name,:role,:email,:wa,:crit,:high,:med,:low,1)
        """), dict(name=name,role=role,email=email,wa=wa,crit=crit,high=high,med=med,low=low))
    print(f"    OK {len(rows)} recipients")

# ─────────────────────────────────────────────────────────────────────────────
# WEBHOOKS
# ─────────────────────────────────────────────────────────────────────────────
async def seed_webhooks(sess):
    print("  -> webhooks...")
    rows = [
        ("Slack Safety Alerts","https://hooks.slack.com/services/DEMO/DEMO/demo",
         "general",json.dumps(["violation.created","fire.detected"]),1),
        ("HRMS Integration","https://hrms.example.com/webhooks/safety",
         "general",json.dumps(["worker.violation","permit.approved"]),1),
        ("ERP Webhook","https://erp.example.com/api/events",
         "general",json.dumps(["all"]),0),
    ]
    for name,url,wtype,events,active in rows:
        await sess.execute(text("""
            INSERT INTO webhooks (name,url,webhook_type,events,secret,active)
            VALUES (:name,:url,:wtype,:events,:secret,:active)
        """), dict(name=name,url=url,wtype=wtype,events=events,
                   secret=f"whsec_{hashlib.sha256(name.encode()).hexdigest()[:16]}",active=active))
    print(f"    OK {len(rows)} webhooks")

# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────
async def seed_audit_log(sess):
    print("  -> audit log...")
    rows = [
        ("permit.approved",  "system",    "permit",    "PTW-20260601-ABC123", "W004 hot_work permit approved by sup-001"),
        ("worker.checkin",   "system",    "worker",    "W001",                "W001 Ravi Kumar checked in via face recognition at site-hq"),
        ("violation.ack",    "safety_off","violation", "550",                  "no hardhat in zone-welding acknowledged"),
        ("org.created",      "admin",     "org",       "org-pharma-hyd",      "New org org-pharma-hyd created with starter plan"),
        ("billing.subscribe","admin",     "billing",   "org-steel-india",     "org-steel-india subscribed to growth plan INR 14999/mo"),
        ("alert.escalated",  "system",    "alert",     "esc-007",             "L2 escalation triggered for W007 no mask chemical zone"),
        ("worker.checkout",  "system",    "worker",    "W002",                "W002 Suresh Raj checkout after 8.5 hours site-hq"),
        ("report.generated", "system",    "report",    "RPT-20260608-0001",   "Incident report generated for no hardhat violation"),
        ("zone.alert",       "system",    "zone",      "zone-chemical",       "Unauthorized entry detected zone-chemical cam-004"),
        ("permit.closed",    "W004",      "permit",    "PTW-20260601-DEF456", "Electrical work completed safely permit closed"),
        ("camera.restart",   "operator",  "camera",    "cam-009",             "cam-009 QC Lab restarted due to stream timeout"),
        ("worker.enroll",    "admin",     "worker",    "W015",                "W015 Karthi Vel face enrolled for recognition"),
    ]
    for action,actor,rtype,rid,details in rows:
        ts = ago(hours=random.randint(1, 96))
        await sess.execute(text("""
            INSERT INTO audit_log (action,actor,resource_type,resource_id,details,created_at)
            VALUES (:action,:actor,:rtype,:rid,:details,:ts)
        """), dict(action=action,actor=actor,rtype=rtype,rid=rid,details=details,
                   ts=ts.strftime("%Y-%m-%d %H:%M:%S")))
    print(f"    OK {len(rows)} audit entries")

# ─────────────────────────────────────────────────────────────────────────────
# ENTERPRISE: orgs, billing, escalation, permits, attendance
# ─────────────────────────────────────────────────────────────────────────────
async def seed_organizations(sess):
    print("  -> organizations...")
    rows = [
        ("org-steel-india",  "ArcelorMittal India",    "steel_manufacturing","active",   "growth",    20,3,25),
        ("org-construct-tn", "L&T Construction TN",    "construction",       "active",   "enterprise",50,10,100),
        ("org-oilgas-rj",    "ONGC Rajasthan",         "oil_gas",            "active",   "enterprise",50,10,100),
        ("org-pharma-hyd",   "Dr. Reddys Hyderabad",   "pharma",             "trial",    "starter",   5,1,10),
        ("org-warehouse-mum","Flipkart Warehouse MUM", "warehouse",          "active",   "growth",    20,3,25),
        ("org-power-mp",     "NTPC Madhya Pradesh",    "power_plant",        "active",   "growth",    20,3,25),
        ("org-demo",         "Demo Factory",           "construction",       "trial",    "starter",   5,1,10),
    ]
    for oid,name,ind,status,plan,cams,sites,users in rows:
        await sess.execute(text("""
            INSERT INTO organizations
                (org_id,org_name,industry_type,country,plan,plan_status,
                 max_cameras,max_sites,max_users,active,admin_email)
            VALUES (:oid,:name,:ind,'IN',:plan,:status,:cams,:sites,:users,1,:email)
            ON CONFLICT(org_id) DO NOTHING
        """), dict(oid=oid,name=name,ind=ind,status=status,plan=plan,
                   cams=cams,sites=sites,users=users,
                   email=f"admin@{oid.split('-',1)[1]}.demo.com"))
    print(f"    OK {len(rows)} organizations")

async def seed_billing(sess):
    print("  -> billing subscriptions...")
    rows = [
        ("org-steel-india",  "growth",    "monthly",1499900),
        ("org-construct-tn", "enterprise","annual", 3599900),
        ("org-oilgas-rj",    "enterprise","monthly",3999900),
        ("org-warehouse-mum","growth",    "annual", 1349900),
        ("org-power-mp",     "growth",    "monthly",1499900),
    ]
    for oid,plan,cycle,amt in rows:
        start = ago(days=30)
        end   = start + timedelta(days=365 if cycle=="annual" else 30)
        await sess.execute(text("""
            INSERT INTO billing_subscriptions
                (org_id,plan,billing_cycle,amount_paise,currency,
                 status,current_period_start,current_period_end)
            VALUES (:oid,:plan,:cycle,:amt,'INR','active',:start,:end)
            ON CONFLICT(org_id) DO NOTHING
        """), dict(oid=oid,plan=plan,cycle=cycle,amt=amt,
                   start=start.strftime("%Y-%m-%d %H:%M:%S"),
                   end=end.strftime("%Y-%m-%d %H:%M:%S")))
    print(f"    OK {len(rows)} subscriptions")

async def seed_model_deployments(sess):
    print("  -> model deployments (MLOps history)...")
    rows = [
        # model_name, version, stage, map50, traffic, frames, status, promoted_days_ago, notes
        ("ppe-detector", "v2.3.1", "Production", 0.912, 100, 45200, "active",     2,  "Promoted after canary passed — +3.2% mAP"),
        ("ppe-detector", "v2.3.0", "Archived",   0.884, 0,   38900, "retired",    18, "Superseded by v2.3.1"),
        ("ppe-detector", "v2.2.5", "Archived",   0.871, 0,   41100, "retired",    35, "Baseline production model"),
        ("ppe-detector", "v2.4.0", "Staging",    0.923, 10,  3400,  "canary",     0,  "Canary @ 10% traffic — evaluating"),
        ("ppe-detector", "v2.3.2", "Archived",   0.889, 0,   12000, "rolled_back",9,  "Rolled back: latency regression +18%"),
    ]
    count = 0
    for name, ver, stage, map50, traffic, frames, status, days, notes in rows:
        promoted = ago(days=days) if status in ("active","retired") else None
        rolled   = ago(days=days) if status == "rolled_back" else None
        await sess.execute(text("""
            INSERT INTO model_deployments
                (model_name,model_version,stage,deploy_type,map50,
                 canary_traffic_pct,canary_frames,traffic_pct,status,
                 deployed_by,promoted_at,rolled_back_at,rollback_reason,notes,
                 deployed_at,created_at)
            VALUES
                (:name,:ver,:stage,:dtype,:map50,
                 :traffic,:frames,:traffic,:status,
                 :by,:promoted,:rolled,:rreason,:notes,
                 :deployed,:created)
        """), dict(
            name=name, ver=ver, stage=stage,
            dtype="canary" if status=="canary" else "full",
            map50=map50, traffic=traffic, frames=frames, status=status,
            by="mlops_admin",
            promoted=promoted.strftime("%Y-%m-%d %H:%M:%S") if promoted else None,
            rolled=rolled.strftime("%Y-%m-%d %H:%M:%S") if rolled else None,
            rreason=notes if status=="rolled_back" else None,
            notes=notes,
            deployed=ago(days=days+1).strftime("%Y-%m-%d %H:%M:%S"),
            created=ago(days=days+1).strftime("%Y-%m-%d %H:%M:%S"),
        ))
        count += 1
    print(f"    OK {count} deployments")

async def seed_drift_results(sess):
    print("  -> drift detection results...")
    for i in range(8):
        ts = ago(days=i*3)
        dscore = round(random.uniform(0.05, 0.28), 3)
        thresh = 0.2
        await sess.execute(text("""
            INSERT INTO drift_results
                (model_version,drift_type,drift_score,threshold,is_drift,details,recorded_at)
            VALUES (:ver,:dtype,:score,:thresh,:isd,:details,:ts)
        """), dict(
            ver="v2.3.1",
            dtype=random.choice(["PSI","KS","confidence"]),
            score=dscore, thresh=thresh,
            isd=1 if dscore > thresh else 0,
            details=json.dumps({"feature":"confidence_dist","samples":random.randint(500,2000)}),
            ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    print("    OK 8 drift results")

async def seed_zone_alerts(sess):
    print("  -> zone alerts...")
    zones = [
        ("zone-welding",   "Welding Bay"),
        ("zone-chemical",  "Chemical Store"),
        ("zone-boiler",    "Boiler Room"),
        ("zone-crane",     "Crane Area"),
        ("zone-floor-1",   "Production Floor"),
    ]
    atypes = ["unauthorized_entry","ppe_violation","overcrowding","restricted_zone_breach","dwell_exceeded"]
    count = 0
    for i in range(14):
        zid, zname = random.choice(zones)
        atype = random.choice(atypes)
        sev   = random.choice(SEVERITIES)
        ack   = random.random() > 0.4
        ts    = ago(hours=random.randint(1, 120))
        await sess.execute(text("""
            INSERT INTO zone_alerts
                (zone_id,zone_name,alert_type,message,severity,
                 acknowledged,acknowledged_by,acknowledged_at,created_at)
            VALUES (:zid,:zname,:atype,:msg,:sev,:ack,:ackby,:ackat,:ts)
        """), dict(
            zid=zid, zname=zname, atype=atype,
            msg=f"{atype.replace('_',' ').title()} detected in {zname}",
            sev=sev, ack=1 if ack else 0,
            ackby="safety_officer" if ack else None,
            ackat=(ts+timedelta(minutes=random.randint(3,30))).strftime("%Y-%m-%d %H:%M:%S") if ack else None,
            ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
        ))
        count += 1
    print(f"    OK {count} zone alerts")

async def seed_escalations(sess):
    print("  -> alert escalations...")
    r = await sess.execute(text("SELECT id FROM violation_events ORDER BY id DESC LIMIT 20"))
    vids = [row[0] for row in r.fetchall()]
    if not vids:
        print("    -- no violations yet, skip")
        return
    count = 0
    for vid in vids[:15]:
        level  = random.choices([1,2,3,4], weights=[40,30,20,10])[0]
        status = random.choice(["open","acknowledged","resolved","open","open"])
        notif  = ago(minutes=random.randint(5,480))
        ack_at = (notif + timedelta(minutes=random.randint(2,30))) if status!="open" else None
        await sess.execute(text("""
            INSERT INTO alert_escalations
                (violation_id,org_id,site_id,level,status,
                 notified_at,acknowledged_by,acknowledged_at,escalation_reason)
            VALUES (:vid,:oid,:sid,:level,:status,:notif,:ackby,:ackat,:reason)
        """), dict(
            vid=vid, oid="org-steel-india", sid="site-hq",
            level=level, status=status,
            notif=notif.strftime("%Y-%m-%d %H:%M:%S"),
            ackby="safety_officer" if status!="open" else None,
            ackat=ack_at.strftime("%Y-%m-%d %H:%M:%S") if ack_at else None,
            reason=f"L{level} auto-escalation — {random.choice(VIOLATION_CLASSES)} detected",
        ))
        count += 1
    print(f"    OK {count} escalations")

async def seed_permits(sess):
    print("  -> permits to work...")
    rows = [
        ("W001","sup-001","hot_work",       "approved",  0),
        ("W004","sup-002","electrical",     "active",    0),
        ("W005","sup-001","height_work",    "active",    0),
        ("W007","sup-003","chemical",       "approved",  2),
        ("W009","sup-002","confined_space", "pending",   3),
        ("W002","sup-001","general",        "closed",   -1),
        ("W013","sup-003","hot_work",       "active",    0),
        ("W010","sup-002","electrical",     "pending",   2),
        ("W008","sup-001","cold_work",      "approved",  1),
        ("W003","sup-003","radiation",      "closed",   -2),
        ("W011","sup-001","excavation",     "active",    0),
        ("W006","sup-002","general",        "active",    0),
    ]
    count = 0
    for wid,sup,wtype,status,day_offset in rows:
        date_str = now().strftime("%Y%m%d")
        rand_hex = hashlib.sha256(f"{wid}{wtype}{count}".encode()).hexdigest()[:6].upper()
        pid  = f"PTW-{date_str}-{rand_hex}"
        qr   = f"PTW-QR:{pid}:{rand_hex[:12]}"
        vf   = ago(hours=random.randint(1,8)) if status in ("active","closed") else now()+timedelta(hours=day_offset*8)
        vu   = vf + timedelta(hours=8)
        await sess.execute(text("""
            INSERT INTO permits_to_work
                (permit_id,org_id,site_id,zone_id,work_type,worker_id,supervisor_id,
                 status,valid_from,valid_until,qr_code,created_at)
            VALUES
                (:pid,:oid,:site,:zone,:wtype,:wid,:sup,
                 :status,:vf,:vu,:qr,:created)
            ON CONFLICT(permit_id) DO NOTHING
        """), dict(
            pid=pid, oid="org-steel-india", site="site-hq",
            zone="zone-welding", wtype=wtype, wid=wid, sup=sup,
            status=status,
            vf=vf.strftime("%Y-%m-%d %H:%M:%S"),
            vu=vu.strftime("%Y-%m-%d %H:%M:%S"),
            qr=qr,
            created=ago(hours=random.randint(1,48)).strftime("%Y-%m-%d %H:%M:%S"),
        ))
        count += 1
    print(f"    OK {count} permits")

async def seed_attendance(sess):
    print("  -> attendance (7-day history + today active)...")
    workers = [
        ("W001","site-hq"),("W002","site-hq"),("W004","site-hq"),
        ("W005","site-east"),("W007","site-west"),("W008","site-hq"),
        ("W009","site-power"),("W010","site-power"),("W011","site-west"),
        ("W013","site-hq"),
    ]
    count = 0
    methods = ["face_recognition","badge","face_recognition","badge","manual"]

    # Historical 7 days (complete)
    for day in range(7, 0, -1):
        d = ago(days=day)
        ci_base = d.replace(hour=7, minute=0, second=0, microsecond=0)
        for wid, site in random.sample(workers, k=random.randint(6, len(workers))):
            ci = ci_base + timedelta(minutes=random.randint(-10,30))
            co = ci + timedelta(hours=random.uniform(7.5, 9.5))
            await sess.execute(text("""
                INSERT INTO worker_attendance
                    (worker_id,org_id,site_id,shift_id,check_in,check_out,entry_method)
                VALUES (:wid,'org-steel-india',:site,'shift-morning',:ci,:co,:method)
            """), dict(wid=wid,site=site,
                       ci=ci.strftime("%Y-%m-%d %H:%M:%S"),
                       co=co.strftime("%Y-%m-%d %H:%M:%S"),
                       method=random.choice(methods)))
            count += 1

    # Today — currently on site (no checkout)
    today_ci = now().replace(hour=7, minute=0, second=0, microsecond=0)
    active = random.sample(workers, k=random.randint(6, 9))
    for wid, site in active:
        ci = today_ci + timedelta(minutes=random.randint(-5,45))
        await sess.execute(text("""
            INSERT INTO worker_attendance
                (worker_id,org_id,site_id,shift_id,check_in,entry_method)
            VALUES (:wid,'org-steel-india',:site,'shift-morning',:ci,:method)
        """), dict(wid=wid,site=site,
                   ci=ci.strftime("%Y-%m-%d %H:%M:%S"),
                   method=random.choice(methods)))
        count += 1

    print(f"    OK {count} records ({len(active)} on site right now)")

# ─────────────────────────────────────────────────────────────────────────────
# VERIFY
# ─────────────────────────────────────────────────────────────────────────────
async def verify():
    print("\n--- VERIFICATION ---")
    tables = [
        ("organizations",       5),
        ("billing_subscriptions",3),
        ("sites",               3),
        ("camera_zones",        5),
        ("camera_registry",     5),
        ("worker_profiles",     10),
        ("shifts",              3),
        ("violation_events",    50),
        ("fire_hazard_events",  3),
        ("proximity_alerts",    5),
        ("pose_hazard_events",  5),
        ("incident_reports",    5),
        ("alert_recipients",    2),
        ("webhooks",            1),
        ("audit_log",           5),
        ("permits_to_work",     5),
        ("worker_attendance",   10),
        ("alert_escalations",   5),
        ("zone_alerts",         5),
        ("model_deployments",   3),
        ("drift_results",       5),
        ("industry_ppe_profiles",15),
    ]
    all_ok = True
    async with AsyncSessionLocal() as s:
        for table, need in tables:
            r = await s.execute(text(f"SELECT COUNT(*) FROM {table}"))
            n = r.scalar()
            ok = n >= need
            if not ok: all_ok = False
            mark = "OK" if ok else "EMPTY"
            print(f"  [{mark:5s}] {table:<30s} {n:>5d} rows")
    print()
    if all_ok:
        print("ALL TABLES OK — Demo fully seeded!")
    else:
        print("Some tables below threshold — check output")
    return all_ok

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
async def run_seed(reset=False):
    print("\nIndustrial Safety Monitor — Demo Data Seeder")
    print("=" * 50)
    await init_db()

    async with AsyncSessionLocal() as sess:
        if reset:
            print("Resetting demo tables...")
            drop = ["alert_escalations","zone_alerts","model_deployments","drift_results","worker_attendance","permits_to_work",
                    "pose_hazard_events","proximity_alerts","fire_hazard_events",
                    "violation_events","incident_reports","audit_log",
                    "webhooks","alert_recipients","billing_subscriptions",
                    "organizations"]
            for t in drop:
                try:
                    await sess.execute(text(f"DELETE FROM {t}"))
                except: pass
            await sess.commit()
            print("  Reset done")

        print("\nSeeding...")
        try:
            await seed_organizations(sess)
            await seed_billing(sess)
            await seed_sites(sess)
            await seed_zones(sess)
            await seed_cameras(sess)
            await seed_workers(sess)
            await seed_shifts(sess)
            await sess.commit()
            print("  [phase 1 ok]")

            await seed_violations(sess)
            await sess.commit()
            print("  [phase 2 ok]")

            await seed_fire_events(sess)
            await seed_proximity_alerts(sess)
            await seed_pose_hazards(sess)
            await seed_reports(sess)
            await seed_alert_recipients(sess)
            await seed_webhooks(sess)
            await seed_audit_log(sess)
            await sess.commit()
            print("  [phase 3 ok]")

            await seed_zone_alerts(sess)
            await seed_model_deployments(sess)
            await seed_drift_results(sess)
            await seed_escalations(sess)
            await seed_permits(sess)
            await seed_attendance(sess)
            await sess.commit()
            print("  [phase 4 ok]")

        except Exception as e:
            await sess.rollback()
            import traceback; traceback.print_exc()
            print(f"\nSeed failed: {e}")
            return False

    print("\nSeeding complete!")
    return True


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true")
    p.add_argument("--check", action="store_true")
    a = p.parse_args()

    if a.check:
        await verify()
    else:
        ok = await run_seed(reset=a.reset)
        if ok:
            await verify()


if __name__ == "__main__":
    asyncio.run(main())
