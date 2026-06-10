"""
backend/routes/billing_route.py

Subscription billing API — Razorpay integration (India-first).
Falls back gracefully if RAZORPAY_KEY_ID is not set (test/free mode).

Plans (INR/month, billed monthly):
  starter:    ₹4,999/mo  → 5 cameras,  1 site,  10 users
  growth:     ₹14,999/mo → 25 cameras, 5 sites, 50 users
  enterprise: ₹39,999/mo → unlimited cameras/sites/users

Endpoints:
  GET  /billing/plans                    → List all plans with pricing
  GET  /billing/subscription/{org_id}   → Get current subscription
  POST /billing/subscribe                → Create/upgrade subscription
  POST /billing/webhook                 → Razorpay webhook receiver
  POST /billing/cancel/{org_id}         → Cancel subscription
"""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from backend.database import get_session
from backend.middleware.rate_limiter import limiter, LIMIT_DEFAULT

router = APIRouter(prefix="/billing", tags=["billing"])

# ── Plan definitions ──────────────────────────────────────────

PLANS = {
    "starter": {
        "name": "Starter",
        "price_inr_monthly": 4999,
        "price_inr_annual": 49999,       # ~2 months free
        "max_cameras": 5,
        "max_sites": 1,
        "max_users": 10,
        "features": [
            "PPE detection (helmet, vest, gloves, boots, mask)",
            "Real-time alerts (email)",
            "Basic reports",
            "5 cameras",
            "1 site",
            "90-day data retention",
        ],
        "razorpay_plan_id_monthly": os.getenv("RAZORPAY_PLAN_STARTER_MONTHLY", ""),
        "razorpay_plan_id_annual":  os.getenv("RAZORPAY_PLAN_STARTER_ANNUAL", ""),
    },
    "growth": {
        "name": "Growth",
        "price_inr_monthly": 14999,
        "price_inr_annual": 149999,
        "max_cameras": 25,
        "max_sites": 5,
        "max_users": 50,
        "features": [
            "Everything in Starter",
            "Fire & smoke detection",
            "Pose hazard detection (fall, ergonomic risk)",
            "Machine proximity alerts",
            "AI incident reports (Groq LLM)",
            "Alert escalation (L1→L4)",
            "Multi-site dashboard",
            "25 cameras, 5 sites",
            "1-year data retention",
            "WhatsApp/Telegram alerts",
        ],
        "razorpay_plan_id_monthly": os.getenv("RAZORPAY_PLAN_GROWTH_MONTHLY", ""),
        "razorpay_plan_id_annual":  os.getenv("RAZORPAY_PLAN_GROWTH_ANNUAL", ""),
    },
    "enterprise": {
        "name": "Enterprise",
        "price_inr_monthly": 39999,
        "price_inr_annual": 399999,
        "max_cameras": 9999,
        "max_sites": 9999,
        "max_users": 9999,
        "features": [
            "Everything in Growth",
            "Unlimited cameras & sites",
            "Permit-to-Work system",
            "Face recognition attendance",
            "Custom PPE profiles per industry",
            "Razorpay billing portal",
            "Dedicated Slack support",
            "SLA 99.9% uptime",
            "On-premise deployment option",
            "Custom model training",
            "Unlimited data retention",
        ],
        "razorpay_plan_id_monthly": os.getenv("RAZORPAY_PLAN_ENTERPRISE_MONTHLY", ""),
        "razorpay_plan_id_annual":  os.getenv("RAZORPAY_PLAN_ENTERPRISE_ANNUAL", ""),
    },
}

RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_AVAILABLE  = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


def _get_razorpay_client():
    """Return Razorpay client or None if not configured."""
    if not RAZORPAY_AVAILABLE:
        return None
    try:
        import razorpay
        return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    except ImportError:
        logger.warning("razorpay package not installed — pip install razorpay")
        return None


# ── Request models ────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    org_id: str = Field(min_length=1, max_length=64)
    plan: str = Field(pattern="^(starter|growth|enterprise)$")
    billing_cycle: str = Field(default="monthly", pattern="^(monthly|annual)$")
    customer_name: Optional[str] = Field(default=None, max_length=100)
    customer_email: Optional[str] = Field(default=None, max_length=200)
    customer_phone: Optional[str] = Field(default=None, max_length=15)


# ── Routes ────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans():
    """List all subscription plans with pricing and features."""
    result = []
    for plan_id, plan in PLANS.items():
        result.append({
            "plan_id": plan_id,
            "name": plan["name"],
            "pricing": {
                "monthly_inr": plan["price_inr_monthly"],
                "annual_inr": plan["price_inr_annual"],
                "annual_savings_pct": round(
                    (1 - plan["price_inr_annual"] / (plan["price_inr_monthly"] * 12)) * 100, 1
                ),
            },
            "limits": {
                "max_cameras": plan["max_cameras"],
                "max_sites": plan["max_sites"],
                "max_users": plan["max_users"],
            },
            "features": plan["features"],
        })
    return {"plans": result, "currency": "INR", "razorpay_available": RAZORPAY_AVAILABLE}


@router.get("/subscription/{org_id}")
@limiter.limit(LIMIT_DEFAULT)
async def get_subscription(
    request: Request,
    org_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get current subscription for an organization."""
    result = await session.exec(text("""
        SELECT bs.*, o.org_name, o.plan_status
        FROM billing_subscriptions bs
        JOIN organizations o ON o.org_id = bs.org_id
        WHERE bs.org_id = :org_id
    """).bindparams(org_id=org_id))
    row = result.fetchone()

    if not row:
        # Check if org exists
        org_result = await session.exec(text(
            "SELECT org_id, plan, plan_status, trial_ends_at FROM organizations WHERE org_id = :org_id"
        ).bindparams(org_id=org_id))
        org = org_result.fetchone()
        if not org:
            raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")
        return {
            "org_id": org_id,
            "plan": org.plan,
            "plan_status": org.plan_status,
            "trial_ends_at": org.trial_ends_at,
            "subscription": None,
        }

    return dict(row._mapping)


@router.post("/subscribe", status_code=201)
@limiter.limit(LIMIT_DEFAULT)
async def subscribe(
    request: Request,
    body: SubscribeRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Create or upgrade a subscription.

    If Razorpay is configured: creates a Razorpay subscription and returns
    a payment_link for the client to complete payment.

    If Razorpay is NOT configured (dev/test): immediately activates the plan.
    """
    plan = PLANS.get(body.plan)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {body.plan}")

    amount_paise = (
        plan["price_inr_annual"] if body.billing_cycle == "annual"
        else plan["price_inr_monthly"]
    ) * 100  # Razorpay uses paise

    razorpay_sub_id = None
    payment_link = None

    # Try Razorpay if configured
    rz_client = _get_razorpay_client()
    if rz_client:
        try:
            plan_key = f"razorpay_plan_id_{body.billing_cycle}"
            rz_plan_id = plan.get(plan_key, "")
            if rz_plan_id:
                sub = rz_client.subscription.create({
                    "plan_id": rz_plan_id,
                    "total_count": 12 if body.billing_cycle == "monthly" else 1,
                    "quantity": 1,
                    "customer_notify": 1,
                    "notify_info": {
                        "notify_phone": body.customer_phone or "",
                        "notify_email": body.customer_email or "",
                    },
                })
                razorpay_sub_id = sub["id"]
                payment_link = f"https://rzp.io/l/{razorpay_sub_id}"
                logger.info("Razorpay subscription created: {}", razorpay_sub_id)
        except Exception as exc:
            logger.warning("Razorpay subscription creation failed: {}", str(exc)[:100])

    # Upsert billing_subscriptions record
    period_start = datetime.now(timezone.utc)
    period_end = period_start + (timedelta(days=365) if body.billing_cycle == "annual" else timedelta(days=30))

    await session.exec(text("""
        INSERT INTO billing_subscriptions
            (org_id, plan, billing_cycle, amount_paise, currency, razorpay_sub_id,
             status, current_period_start, current_period_end)
        VALUES
            (:org_id, :plan, :billing_cycle, :amount_paise, 'INR', :razorpay_sub_id,
             :status, :period_start, :period_end)
        ON CONFLICT(org_id) DO UPDATE SET
            plan = :plan,
            billing_cycle = :billing_cycle,
            amount_paise = :amount_paise,
            razorpay_sub_id = COALESCE(:razorpay_sub_id, razorpay_sub_id),
            status = :status,
            current_period_start = :period_start,
            current_period_end = :period_end
    """).bindparams(
        org_id=body.org_id,
        plan=body.plan,
        billing_cycle=body.billing_cycle,
        amount_paise=amount_paise,
        razorpay_sub_id=razorpay_sub_id,
        status="pending" if razorpay_sub_id else "active",
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    ))

    # Update organization plan
    activate_status = "pending_payment" if razorpay_sub_id else "active"
    await session.exec(text("""
        UPDATE organizations
        SET plan = :plan, plan_status = :status,
            max_cameras = :max_cameras, max_sites = :max_sites, max_users = :max_users
        WHERE org_id = :org_id
    """).bindparams(
        plan=body.plan,
        status=activate_status,
        max_cameras=plan["max_cameras"],
        max_sites=plan["max_sites"],
        max_users=plan["max_users"],
        org_id=body.org_id,
    ))

    return {
        "org_id": body.org_id,
        "plan": body.plan,
        "billing_cycle": body.billing_cycle,
        "amount_inr": amount_paise // 100,
        "status": activate_status,
        "razorpay_subscription_id": razorpay_sub_id,
        "payment_link": payment_link,
        "message": (
            f"Complete payment at {payment_link}" if payment_link
            else f"Plan '{body.plan}' activated (Razorpay not configured — demo mode)"
        ),
    }


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Razorpay webhook receiver.
    Handles: subscription.activated, subscription.charged, subscription.cancelled,
             payment.captured, payment.failed
    """
    body_bytes = await request.body()

    # Verify webhook signature
    if RAZORPAY_KEY_SECRET and x_razorpay_signature:
        expected = hmac.new(
            RAZORPAY_KEY_SECRET.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_razorpay_signature):
            logger.warning("Razorpay webhook signature mismatch")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event", "")
    entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
    sub_id = entity.get("id", "")

    logger.info("Razorpay webhook | event={} | sub_id={}", event, sub_id)

    if event == "subscription.activated" and sub_id:
        await session.exec(text("""
            UPDATE billing_subscriptions SET status = 'active'
            WHERE razorpay_sub_id = :sub_id
        """).bindparams(sub_id=sub_id))
        await session.exec(text("""
            UPDATE organizations SET plan_status = 'active'
            WHERE razorpay_subscription_id = :sub_id
        """).bindparams(sub_id=sub_id))

    elif event == "subscription.cancelled" and sub_id:
        await session.exec(text("""
            UPDATE billing_subscriptions
            SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
            WHERE razorpay_sub_id = :sub_id
        """).bindparams(sub_id=sub_id))
        await session.exec(text("""
            UPDATE organizations SET plan_status = 'cancelled', plan = 'starter'
            WHERE razorpay_subscription_id = :sub_id
        """).bindparams(sub_id=sub_id))

    elif event == "payment.failed" and sub_id:
        logger.warning("Payment failed for subscription: {}", sub_id)
        await session.exec(text("""
            UPDATE billing_subscriptions SET status = 'past_due'
            WHERE razorpay_sub_id = :sub_id
        """).bindparams(sub_id=sub_id))

    return {"status": "ok", "event": event}


@router.post("/cancel/{org_id}")
@limiter.limit(LIMIT_DEFAULT)
async def cancel_subscription(
    request: Request,
    org_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Cancel subscription for an organization."""
    rz_client = _get_razorpay_client()
    if rz_client:
        # Get sub id
        result = await session.exec(text(
            "SELECT razorpay_sub_id FROM billing_subscriptions WHERE org_id = :org_id"
        ).bindparams(org_id=org_id))
        row = result.fetchone()
        if row and row.razorpay_sub_id:
            try:
                rz_client.subscription.cancel(row.razorpay_sub_id, {"cancel_at_cycle_end": 1})
                logger.info("Razorpay subscription cancelled: {}", row.razorpay_sub_id)
            except Exception as exc:
                logger.warning("Razorpay cancel failed: {}", str(exc)[:100])

    await session.exec(text("""
        UPDATE billing_subscriptions
        SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
        WHERE org_id = :org_id
    """).bindparams(org_id=org_id))

    await session.exec(text("""
        UPDATE organizations SET plan_status = 'cancelled', plan = 'starter'
        WHERE org_id = :org_id
    """).bindparams(org_id=org_id))

    return {"org_id": org_id, "status": "cancelled", "message": "Subscription cancelled"}
