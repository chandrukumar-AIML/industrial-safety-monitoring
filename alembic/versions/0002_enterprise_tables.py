"""Enterprise tables: organizations, billing, PPE profiles, escalation, permits, attendance

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-08

Adds:
  - organizations         (multi-tenant top-level table)
  - billing_subscriptions (Razorpay subscription tracking)
  - industry_ppe_profiles (industry x zone PPE requirements)
  - alert_escalations     (L1→L4 escalation matrix)
  - permits_to_work       (digital permit-to-work)
  - worker_attendance     (check-in/check-out headcount)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── organizations ─────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String(64), unique=True, nullable=False),
        sa.Column("org_name", sa.String(200), nullable=False),
        sa.Column("industry_type", sa.String(50)),
        sa.Column("country", sa.String(2), server_default="IN"),
        sa.Column("plan", sa.String(20), server_default="starter"),
        sa.Column("plan_status", sa.String(20), server_default="trial"),
        sa.Column("trial_ends_at", sa.DateTime),
        sa.Column("max_cameras", sa.Integer, server_default="5"),
        sa.Column("max_sites", sa.Integer, server_default="1"),
        sa.Column("max_users", sa.Integer, server_default="10"),
        sa.Column("razorpay_customer_id", sa.String(100)),
        sa.Column("razorpay_subscription_id", sa.String(100)),
        sa.Column("admin_email", sa.String(200)),
        sa.Column("active", sa.Boolean, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_org_org_id", "organizations", ["org_id"])
    op.create_index("ix_org_plan_status", "organizations", ["plan_status"])

    # ── billing_subscriptions ─────────────────────────────────
    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String(64), unique=True, nullable=False),
        sa.Column("plan", sa.String(20), nullable=False),
        sa.Column("billing_cycle", sa.String(10), server_default="monthly"),
        sa.Column("amount_paise", sa.Integer, server_default="0"),
        sa.Column("currency", sa.String(3), server_default="INR"),
        sa.Column("razorpay_sub_id", sa.String(100)),
        sa.Column("status", sa.String(20), server_default="trial"),
        sa.Column("current_period_start", sa.DateTime),
        sa.Column("current_period_end", sa.DateTime),
        sa.Column("cancelled_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_billing_org_id", "billing_subscriptions", ["org_id"])

    # ── industry_ppe_profiles ─────────────────────────────────
    op.create_table(
        "industry_ppe_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("industry_type", sa.String(50), nullable=False),
        sa.Column("zone_type", sa.String(50), nullable=False),
        sa.Column("required_ppe", sa.Text, server_default="[]"),
        sa.Column("risk_level", sa.String(16), server_default="HIGH"),
        sa.Column("compliance_standard", sa.String(100), server_default="OSHA 1910.132"),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_ppe_industry", "industry_ppe_profiles", ["industry_type"])
    op.create_index("ix_ppe_zone", "industry_ppe_profiles", ["zone_type"])
    op.create_index(
        "ix_ppe_industry_zone",
        "industry_ppe_profiles",
        ["industry_type", "zone_type"],
    )

    # ── alert_escalations ─────────────────────────────────────
    op.create_table(
        "alert_escalations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("violation_id", sa.Integer, nullable=False),
        sa.Column("org_id", sa.String(64)),
        sa.Column("site_id", sa.String(50)),
        sa.Column("level", sa.Integer, server_default="1"),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("notified_at", sa.DateTime),
        sa.Column("acknowledged_by", sa.String(100)),
        sa.Column("acknowledged_at", sa.DateTime),
        sa.Column("escalation_reason", sa.String(200)),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_esc_violation_id", "alert_escalations", ["violation_id"])
    op.create_index("ix_esc_org_id", "alert_escalations", ["org_id"])
    op.create_index("ix_esc_status", "alert_escalations", ["status"])
    op.create_index("ix_esc_level", "alert_escalations", ["level"])

    # ── permits_to_work ───────────────────────────────────────
    op.create_table(
        "permits_to_work",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("permit_id", sa.String(64), unique=True, nullable=False),
        sa.Column("org_id", sa.String(64)),
        sa.Column("site_id", sa.String(50)),
        sa.Column("zone_id", sa.String(64)),
        sa.Column("work_type", sa.String(100), nullable=False),
        sa.Column("worker_id", sa.String(64)),
        sa.Column("supervisor_id", sa.String(64)),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("valid_from", sa.DateTime),
        sa.Column("valid_until", sa.DateTime),
        sa.Column("approved_by", sa.String(100)),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("qr_code", sa.String(200)),
        sa.Column("risk_assessment", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_ptw_permit_id", "permits_to_work", ["permit_id"])
    op.create_index("ix_ptw_org_id", "permits_to_work", ["org_id"])
    op.create_index("ix_ptw_status", "permits_to_work", ["status"])
    op.create_index("ix_ptw_valid_until", "permits_to_work", ["valid_until"])

    # ── worker_attendance ─────────────────────────────────────
    op.create_table(
        "worker_attendance",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("worker_id", sa.String(64), nullable=False),
        sa.Column("org_id", sa.String(64)),
        sa.Column("site_id", sa.String(50)),
        sa.Column("shift_id", sa.Integer),
        sa.Column("check_in", sa.DateTime),
        sa.Column("check_out", sa.DateTime),
        sa.Column("entry_method", sa.String(30), server_default="face_recognition"),
        sa.Column("entry_camera_id", sa.String(64)),
        sa.Column("exit_camera_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_att_worker_id", "worker_attendance", ["worker_id"])
    op.create_index("ix_att_org_id", "worker_attendance", ["org_id"])
    op.create_index("ix_att_check_in", "worker_attendance", ["check_in"])
    op.create_index("ix_att_site_id", "worker_attendance", ["site_id"])


def downgrade() -> None:
    op.drop_table("worker_attendance")
    op.drop_table("permits_to_work")
    op.drop_table("alert_escalations")
    op.drop_table("industry_ppe_profiles")
    op.drop_table("billing_subscriptions")
    op.drop_table("organizations")
