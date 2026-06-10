"""
tests/test_enterprise.py

Enterprise feature tests — organizations, billing, industry PPE,
escalation, permits, attendance.

Covers all 6 new enterprise route modules.
66 existing tests + these = 100+ tests total.
"""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════
# ORGANIZATIONS
# ═══════════════════════════════════════════════════════════════

class TestOrganizations:

    @pytest.mark.asyncio
    async def test_create_organization(self, client):
        """POST /organizations creates a new org."""
        resp = await client.post("/organizations", json={
            "org_name": "Test Steel Plant Ltd",
            "industry_type": "steel_manufacturing",
            "country": "IN",
            "plan": "starter",
            "admin_email": "admin@testplant.com",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "org_id" in data
        assert data["plan"] == "starter"
        assert data["plan_status"] == "trial"
        assert "trial_ends_at" in data

    @pytest.mark.asyncio
    async def test_list_organizations(self, client):
        """GET /organizations returns a list."""
        resp = await client.get("/organizations")
        assert resp.status_code == 200
        data = resp.json()
        assert "organizations" in data
        assert isinstance(data["organizations"], list)
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_organization_not_found(self, client):
        """GET /organizations/{org_id} returns 404 for unknown org."""
        resp = await client.get("/organizations/nonexistent-org-xyz-999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_organization_found(self, client):
        """Create then retrieve an org by org_id."""
        # Create
        create_resp = await client.post("/organizations", json={
            "org_name": "Pharma Industries Pvt Ltd",
            "industry_type": "pharma",
            "plan": "growth",
        })
        assert create_resp.status_code == 201
        org_id = create_resp.json()["org_id"]

        # Retrieve
        get_resp = await client.get(f"/organizations/{org_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["org_id"] == org_id
        assert data["org_name"] == "Pharma Industries Pvt Ltd"

    @pytest.mark.asyncio
    async def test_update_organization(self, client):
        """PATCH /organizations/{org_id} updates fields."""
        create_resp = await client.post("/organizations", json={
            "org_name": "Old Name Corp",
            "plan": "starter",
        })
        org_id = create_resp.json()["org_id"]

        patch_resp = await client.patch(f"/organizations/{org_id}", json={
            "org_name": "New Name Corp",
            "max_cameras": 20,
        })
        assert patch_resp.status_code == 200
        data = patch_resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_organization_usage(self, client):
        """GET /organizations/{org_id}/usage returns usage stats."""
        create_resp = await client.post("/organizations", json={
            "org_name": "Usage Test Corp",
            "plan": "enterprise",
        })
        org_id = create_resp.json()["org_id"]

        usage_resp = await client.get(f"/organizations/{org_id}/usage")
        assert usage_resp.status_code == 200
        data = usage_resp.json()
        assert "usage" in data
        assert "cameras" in data["usage"]
        assert "sites" in data["usage"]

    @pytest.mark.asyncio
    async def test_activate_organization(self, client):
        """POST /organizations/{org_id}/activate returns ok."""
        create_resp = await client.post("/organizations", json={"org_name": "Activate Test"})
        org_id = create_resp.json()["org_id"]

        resp = await client.post(f"/organizations/{org_id}/activate")
        assert resp.status_code == 200
        assert resp.json()["plan_status"] == "active"

    @pytest.mark.asyncio
    async def test_suspend_organization(self, client):
        """POST /organizations/{org_id}/suspend returns suspended."""
        create_resp = await client.post("/organizations", json={"org_name": "Suspend Test"})
        org_id = create_resp.json()["org_id"]

        resp = await client.post(f"/organizations/{org_id}/suspend")
        assert resp.status_code == 200
        assert resp.json()["plan_status"] == "suspended"

    @pytest.mark.asyncio
    async def test_org_invalid_plan_rejected(self, client):
        """POST /organizations with invalid plan returns 422."""
        resp = await client.post("/organizations", json={
            "org_name": "Bad Plan Corp",
            "plan": "diamond",  # invalid
        })
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# BILLING
# ═══════════════════════════════════════════════════════════════

class TestBilling:

    @pytest.mark.asyncio
    async def test_list_plans(self, client):
        """GET /billing/plans returns all 3 plans."""
        resp = await client.get("/billing/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert "plans" in data
        plan_ids = [p["plan_id"] for p in data["plans"]]
        assert "starter" in plan_ids
        assert "growth" in plan_ids
        assert "enterprise" in plan_ids

    @pytest.mark.asyncio
    async def test_plan_has_pricing(self, client):
        """Each plan has INR pricing and feature list."""
        resp = await client.get("/billing/plans")
        for plan in resp.json()["plans"]:
            assert "pricing" in plan
            assert plan["pricing"]["monthly_inr"] > 0
            assert "features" in plan
            assert len(plan["features"]) > 0

    @pytest.mark.asyncio
    async def test_subscribe_demo_mode(self, client):
        """POST /billing/subscribe activates immediately in demo mode (no Razorpay key)."""
        # Create org first
        org_resp = await client.post("/organizations", json={"org_name": "Billing Test Co"})
        org_id = org_resp.json()["org_id"]

        resp = await client.post("/billing/subscribe", json={
            "org_id": org_id,
            "plan": "growth",
            "billing_cycle": "monthly",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["plan"] == "growth"
        assert data["amount_inr"] == 14999
        # In demo mode (no Razorpay key), status is 'active'
        assert data["status"] in {"active", "pending_payment"}

    @pytest.mark.asyncio
    async def test_get_subscription_org_no_sub(self, client):
        """GET /billing/subscription/{org_id} returns trial info when no sub."""
        org_resp = await client.post("/organizations", json={"org_name": "No Sub Corp"})
        org_id = org_resp.json()["org_id"]

        resp = await client.get(f"/billing/subscription/{org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "plan" in data

    @pytest.mark.asyncio
    async def test_get_subscription_not_found(self, client):
        """GET /billing/subscription/{unknown} returns 404."""
        resp = await client.get("/billing/subscription/nonexistent-org-zzzz")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_subscription(self, client):
        """POST /billing/cancel/{org_id} cancels subscription."""
        org_resp = await client.post("/organizations", json={"org_name": "Cancel Sub Corp"})
        org_id = org_resp.json()["org_id"]

        # Subscribe first
        await client.post("/billing/subscribe", json={
            "org_id": org_id, "plan": "starter", "billing_cycle": "monthly"
        })

        cancel_resp = await client.post(f"/billing/cancel/{org_id}")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"


# ═══════════════════════════════════════════════════════════════
# INDUSTRY PPE
# ═══════════════════════════════════════════════════════════════

class TestIndustryPPE:

    @pytest.mark.asyncio
    async def test_seed_profiles(self, client):
        """POST /industry-ppe/seed inserts default profiles."""
        resp = await client.post("/industry-ppe/seed")
        assert resp.status_code == 201
        data = resp.json()
        assert "inserted" in data
        assert "skipped" in data
        assert data["total"] == 23

    @pytest.mark.asyncio
    async def test_seed_idempotent(self, client):
        """POST /industry-ppe/seed twice doesn't duplicate."""
        await client.post("/industry-ppe/seed")
        resp2 = await client.post("/industry-ppe/seed")
        assert resp2.status_code == 201
        # Second time all should be skipped
        assert resp2.json()["inserted"] == 0

    @pytest.mark.asyncio
    async def test_list_all_profiles(self, client):
        """GET /industry-ppe/profiles returns profiles after seed."""
        await client.post("/industry-ppe/seed")
        resp = await client.get("/industry-ppe/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 23
        assert "industries" in data
        assert "construction" in data["industries"]

    @pytest.mark.asyncio
    async def test_list_profiles_by_industry(self, client):
        """GET /industry-ppe/profiles?industry_type=construction filters correctly."""
        await client.post("/industry-ppe/seed")
        resp = await client.get("/industry-ppe/profiles?industry_type=construction")
        assert resp.status_code == 200
        data = resp.json()
        assert all(p["industry_type"] == "construction" for p in data["profiles"])

    @pytest.mark.asyncio
    async def test_get_industry_profiles(self, client):
        """GET /industry-ppe/profiles/oil_gas returns oil_gas profiles."""
        await client.post("/industry-ppe/seed")
        resp = await client.get("/industry-ppe/profiles/oil_gas")
        assert resp.status_code == 200
        data = resp.json()
        assert data["industry_type"] == "oil_gas"
        assert data["zones"] >= 3

    @pytest.mark.asyncio
    async def test_get_unknown_industry_404(self, client):
        """GET /industry-ppe/profiles/unknown returns 404."""
        resp = await client.get("/industry-ppe/profiles/unknown_industry_xyz")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_compliance_check_is_violation(self, client):
        """GET /industry-ppe/check returns is_violation=true for required PPE."""
        await client.post("/industry-ppe/seed")
        resp = await client.get(
            "/industry-ppe/check?industry_type=construction"
            "&zone_type=general&detected_class=no+hardhat"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_violation"] is True
        assert "no hardhat" in data["required_ppe"]

    @pytest.mark.asyncio
    async def test_compliance_check_not_violation(self, client):
        """Warehouse general zone — no hardhat is NOT required."""
        await client.post("/industry-ppe/seed")
        # Warehouse general: only vest + boots required
        resp = await client.get(
            "/industry-ppe/check?industry_type=warehouse"
            "&zone_type=general&detected_class=no+hardhat"
        )
        assert resp.status_code == 200
        data = resp.json()
        # no hardhat not required for warehouse general
        assert data["is_violation"] is False

    @pytest.mark.asyncio
    async def test_create_custom_profile(self, client):
        """POST /industry-ppe/profiles creates a custom profile."""
        resp = await client.post("/industry-ppe/profiles", json={
            "industry_type": "textile",
            "zone_type": "dyeing",
            "required_ppe": ["no gloves", "no mask", "no goggles"],
            "risk_level": "HIGH",
            "compliance_standard": "Factories Act 1948",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["industry_type"] == "textile"


# ═══════════════════════════════════════════════════════════════
# ESCALATION
# ═══════════════════════════════════════════════════════════════

class TestEscalation:

    @pytest.mark.asyncio
    async def test_list_open_escalations_empty(self, client):
        """GET /escalation/open returns empty list initially."""
        resp = await client.get("/escalation/open")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert isinstance(data["alerts"], list)
        assert "escalation_levels" in data

    @pytest.mark.asyncio
    async def test_manual_trigger_escalation(self, client):
        """POST /escalation/trigger/{id} creates L1 escalation."""
        resp = await client.post("/escalation/trigger/9999?org_id=test-org&site_id=site-1")
        assert resp.status_code == 201
        data = resp.json()
        assert data["level"] == 1
        assert data["status"] in {"created", "already_exists"}

    @pytest.mark.asyncio
    async def test_trigger_idempotent(self, client):
        """Triggering escalation twice returns already_exists."""
        await client.post("/escalation/trigger/8888")
        resp2 = await client.post("/escalation/trigger/8888")
        assert resp2.status_code == 201
        assert resp2.json()["status"] == "already_exists"

    @pytest.mark.asyncio
    async def test_escalation_stats(self, client):
        """GET /escalation/stats/summary returns stats dict."""
        resp = await client.get("/escalation/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_level" in data

    @pytest.mark.asyncio
    async def test_get_escalation_not_found(self, client):
        """GET /escalation/{id} returns 404 for unknown violation."""
        resp = await client.get("/escalation/99999999")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# PERMITS TO WORK
# ═══════════════════════════════════════════════════════════════

class TestPermits:

    @pytest.mark.asyncio
    async def test_request_permit(self, client):
        """POST /permits creates a pending permit."""
        resp = await client.post("/permits", json={
            "work_type": "hot_work",
            "zone_id": "furnace-zone-1",
            "worker_id": "W-001",
            "supervisor_id": "S-001",
            "org_id": "test-org",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "permit_id" in data
        assert data["permit_id"].startswith("PTW-")
        assert data["status"] == "pending"
        assert data["risk_level"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_request_invalid_work_type(self, client):
        """POST /permits with invalid work_type returns 400."""
        resp = await client.post("/permits", json={
            "work_type": "flying_cars",
            "worker_id": "W-001",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_permits(self, client):
        """GET /permits returns list."""
        resp = await client.get("/permits")
        assert resp.status_code == 200
        data = resp.json()
        assert "permits" in data
        assert isinstance(data["permits"], list)

    @pytest.mark.asyncio
    async def test_approve_permit(self, client):
        """POST /permits/{id}/approve sets status to active."""
        # Create
        create_resp = await client.post("/permits", json={
            "work_type": "confined_space",
            "worker_id": "W-002",
        })
        permit_id = create_resp.json()["permit_id"]

        # Approve
        approve_resp = await client.post(f"/permits/{permit_id}/approve", json={
            "approved_by": "safety-officer-001",
            "valid_hours": 8,
        })
        assert approve_resp.status_code == 200
        data = approve_resp.json()
        assert data["status"] == "active"
        assert "qr_code" in data
        assert data["qr_code"].startswith("PTW-QR:")

    @pytest.mark.asyncio
    async def test_validate_permit_active(self, client):
        """GET /permits/validate/{id} returns allowed=true for active permit."""
        create_resp = await client.post("/permits", json={
            "work_type": "electrical", "worker_id": "W-003",
        })
        permit_id = create_resp.json()["permit_id"]

        await client.post(f"/permits/{permit_id}/approve", json={
            "approved_by": "supervisor-001", "valid_hours": 4,
        })

        validate_resp = await client.get(f"/permits/validate/{permit_id}")
        assert validate_resp.status_code == 200
        assert validate_resp.json()["allowed"] is True

    @pytest.mark.asyncio
    async def test_validate_permit_pending(self, client):
        """Pending permit (not approved) → allowed=false."""
        create_resp = await client.post("/permits", json={
            "work_type": "height_work", "worker_id": "W-004",
        })
        permit_id = create_resp.json()["permit_id"]

        validate_resp = await client.get(f"/permits/validate/{permit_id}")
        assert validate_resp.json()["allowed"] is False

    @pytest.mark.asyncio
    async def test_cancel_permit(self, client):
        """POST /permits/{id}/cancel returns cancelled."""
        create_resp = await client.post("/permits", json={
            "work_type": "chemical", "worker_id": "W-005",
        })
        permit_id = create_resp.json()["permit_id"]

        cancel_resp = await client.post(f"/permits/{permit_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_close_permit(self, client):
        """POST /permits/{id}/close on active permit returns closed."""
        create_resp = await client.post("/permits", json={
            "work_type": "general", "worker_id": "W-006",
        })
        permit_id = create_resp.json()["permit_id"]
        await client.post(f"/permits/{permit_id}/approve", json={
            "approved_by": "sup-001", "valid_hours": 2,
        })

        close_resp = await client.post(f"/permits/{permit_id}/close")
        assert close_resp.status_code == 200
        assert close_resp.json()["status"] == "closed"

    @pytest.mark.asyncio
    async def test_expired_permits_list(self, client):
        """GET /permits/expired/list returns list (may be empty)."""
        resp = await client.get("/permits/expired/list")
        assert resp.status_code == 200
        assert "expired_permits" in resp.json()


# ═══════════════════════════════════════════════════════════════
# ATTENDANCE
# ═══════════════════════════════════════════════════════════════

class TestAttendance:

    @pytest.mark.asyncio
    async def test_check_in(self, client):
        """POST /attendance/checkin records worker check-in."""
        resp = await client.post("/attendance/checkin", json={
            "worker_id": "ATT-W-001",
            "site_id": "plant-1",
            "entry_method": "manual",
            "org_id": "test-org",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["worker_id"] == "ATT-W-001"
        assert data["status"] == "checked_in"
        assert "check_in" in data

    @pytest.mark.asyncio
    async def test_double_checkin_rejected(self, client):
        """Second check-in without checkout returns 409."""
        await client.post("/attendance/checkin", json={
            "worker_id": "ATT-W-002", "site_id": "plant-1", "entry_method": "manual"
        })
        resp2 = await client.post("/attendance/checkin", json={
            "worker_id": "ATT-W-002", "site_id": "plant-1", "entry_method": "manual"
        })
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_check_out(self, client):
        """POST /attendance/checkout closes check-in and calculates hours."""
        await client.post("/attendance/checkin", json={
            "worker_id": "ATT-W-003", "site_id": "plant-1", "entry_method": "manual"
        })
        resp = await client.post("/attendance/checkout", json={
            "worker_id": "ATT-W-003",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "checked_out"
        assert "check_out" in data
        assert data["hours_worked"] is not None
        assert data["hours_worked"] >= 0

    @pytest.mark.asyncio
    async def test_checkout_no_checkin_returns_404(self, client):
        """Checkout without checkin returns 404."""
        resp = await client.post("/attendance/checkout", json={
            "worker_id": "NOBODY-XXXX-9999",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_headcount(self, client):
        """GET /attendance/headcount returns count of on-site workers."""
        # Check-in a worker
        await client.post("/attendance/checkin", json={
            "worker_id": "ATT-W-HCOUNT", "site_id": "site-hcount", "entry_method": "manual"
        })
        resp = await client.get("/attendance/headcount?site_id=site-hcount")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_on_site" in data
        assert data["total_on_site"] >= 1

    @pytest.mark.asyncio
    async def test_active_workers(self, client):
        """GET /attendance/active returns currently on-site workers."""
        resp = await client.get("/attendance/active")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "workers_on_site" in data

    @pytest.mark.asyncio
    async def test_today_attendance(self, client):
        """GET /attendance/today returns today's log."""
        resp = await client.get("/attendance/today")
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "total_checked_in" in data
        assert "records" in data

    @pytest.mark.asyncio
    async def test_worker_history(self, client):
        """GET /attendance/worker/{id} returns history."""
        resp = await client.get("/attendance/worker/ATT-W-001")
        assert resp.status_code == 200
        data = resp.json()
        assert "worker_id" in data
        assert "records" in data
        assert "total_hours" in data

    @pytest.mark.asyncio
    async def test_muster_drill(self, client):
        """POST /attendance/muster returns on-site snapshot."""
        resp = await client.post("/attendance/muster")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "MUSTER_COMPLETE"
        assert "total_on_site" in data
        assert "workers" in data
        assert "muster_time" in data
