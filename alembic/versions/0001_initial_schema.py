"""Initial schema — all 12 tables with indexes

Role: DBA
Revision ID: 0001
Revises: (none — first migration)
Create Date: 2025-06-08

This migration:
1. Creates all 12 core tables
2. Adds performance indexes on frequently-queried columns
3. Sets correct column defaults (fixes previous manual ALTER scripts)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers
revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables and indexes from scratch."""

    # ── violation_events ─────────────────────────────────────
    op.create_table(
        "violation_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("class_name", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("zone_id", sa.String(64), nullable=True),
        sa.Column("bbox_x1", sa.Float, nullable=False, server_default="0"),
        sa.Column("bbox_y1", sa.Float, nullable=False, server_default="0"),
        sa.Column("bbox_x2", sa.Float, nullable=False, server_default="0"),
        sa.Column("bbox_y2", sa.Float, nullable=False, server_default="0"),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("acknowledged_by", sa.String(64), nullable=True),
        sa.Column("camera_id", sa.String(64), nullable=True),
        sa.Column("frame_idx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_violation_events_timestamp", "violation_events", ["timestamp"])
    op.create_index("ix_violation_events_class_name", "violation_events", ["class_name"])
    op.create_index("ix_violation_events_zone_id", "violation_events", ["zone_id"])
    op.create_index("ix_violation_events_track_id", "violation_events", ["track_id"])

    # ── worker_profiles ───────────────────────────────────────
    op.create_table(
        "worker_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("worker_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("department", sa.String(64), nullable=True),
        sa.Column("role", sa.String(64), nullable=True),
        sa.Column("face_embedding", sa.Text, nullable=True),
        sa.Column("risk_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("violation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hr_alert_sent", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("hr_alert_sent_at", sa.DateTime, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_worker_profiles_worker_id", "worker_profiles", ["worker_id"])
    op.create_index("ix_worker_profiles_risk_score", "worker_profiles", ["risk_score"])

    # ── worker_violations (junction) ─────────────────────────
    op.create_table(
        "worker_violations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("worker_id", sa.String(64), nullable=False),
        sa.Column("violation_id", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["violation_id"], ["violation_events.id"]),
    )
    op.create_index("ix_worker_violations_worker_id", "worker_violations", ["worker_id"])

    # ── camera_registry ───────────────────────────────────────
    op.create_table(
        "camera_registry",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("rtsp_url", sa.String(512), nullable=False),
        sa.Column("location", sa.String(128), nullable=True),
        sa.Column("zone_id", sa.String(64), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="offline"),
        sa.Column("fps_actual", sa.Float, nullable=True),
        sa.Column("reconnect_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_seen", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_camera_registry_camera_id", "camera_registry", ["camera_id"])

    # ── camera_zones ─────────────────────────────────────────
    op.create_table(
        "camera_zones",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("zone_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("zone_type", sa.String(32), nullable=False, server_default="restricted"),
        sa.Column("camera_id", sa.String(64), nullable=True),
        sa.Column("polygon", sa.Text, nullable=True),
        sa.Column("required_ppe", sa.Text, nullable=True),
        sa.Column("risk_multiplier", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_camera_zones_zone_id", "camera_zones", ["zone_id"])

    # ── agent_runs ────────────────────────────────────────────
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column("violation_id", sa.Integer, nullable=True),
        sa.Column("track_id", sa.Integer, nullable=True),
        sa.Column("class_name", sa.String(64), nullable=True),
        sa.Column("severity_score", sa.Float, nullable=True),
        sa.Column("alert_level", sa.String(16), nullable=True),
        sa.Column("report_id", sa.Integer, nullable=True),
        sa.Column("alert_sent", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("compliance_delta", sa.Float, nullable=True),
        sa.Column("final_status", sa.String(32), nullable=True),
        sa.Column("trace_steps", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_agent_runs_run_id", "agent_runs", ["run_id"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])

    # ── incident_reports ─────────────────────────────────────
    op.create_table(
        "incident_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("violation_id", sa.Integer, nullable=True),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("track_id", sa.Integer, nullable=True),
        sa.Column("class_name", sa.String(64), nullable=True),
        sa.Column("zone_id", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("incident_summary", sa.Text, nullable=True),
        sa.Column("root_cause_analysis", sa.Text, nullable=True),
        sa.Column("corrective_actions", sa.Text, nullable=True),
        sa.Column("narrative", sa.Text, nullable=True),
        sa.Column("osha_reference", sa.String(128), nullable=True),
        sa.Column("severity_level", sa.String(16), nullable=True),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("actions_taken", sa.Text, nullable=True),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("generation_ms", sa.Float, nullable=True),
        sa.Column("pdf_path", sa.String(256), nullable=True),
        sa.Column("pdf_size_bytes", sa.Integer, nullable=True),
        sa.Column("report_json", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="generated"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_incident_reports_created_at", "incident_reports", ["created_at"])
    op.create_index("ix_incident_reports_zone_id", "incident_reports", ["zone_id"])

    # ── audit_log ─────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=True),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_actor", "audit_log", ["actor"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    # ── webhooks ──────────────────────────────────────────────
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("secret", sa.String(128), nullable=True),
        sa.Column("events", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_triggered_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ── model_deployments ─────────────────────────────────────
    op.create_table(
        "model_deployments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False, server_default="production"),
        sa.Column("deploy_type", sa.String(32), nullable=True),
        sa.Column("map50", sa.Float, nullable=True),
        sa.Column("canary_traffic_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("canary_frames", sa.Integer, nullable=False, server_default="0"),
        sa.Column("traffic_pct", sa.Float, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("deployed_by", sa.String(64), nullable=True),
        sa.Column("promoted_at", sa.DateTime, nullable=True),
        sa.Column("rolled_back_at", sa.DateTime, nullable=True),
        sa.Column("rollback_reason", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("deployed_at", sa.DateTime, nullable=True),
        sa.Column("retired_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_model_deployments_stage", "model_deployments", ["stage"])

    # ── sites ─────────────────────────────────────────────────
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("location", sa.String(256), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_sites_site_id", "sites", ["site_id"])

    # ── shifts ────────────────────────────────────────────────
    op.create_table(
        "shifts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("start_time", sa.String(8), nullable=False),
        sa.Column("end_time", sa.String(8), nullable=False),
        sa.Column("days", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_shifts_site_id", "shifts", ["site_id"])

    # ── pose_hazard_events ────────────────────────────────────
    op.create_table(
        "pose_hazard_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("hazard_type", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("zone_id", sa.String(64), nullable=True),
        sa.Column("landmark_data", sa.Text, nullable=True),
        sa.Column("combined_alert", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("frame_idx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_pose_hazard_events_timestamp", "pose_hazard_events", ["timestamp"])
    op.create_index("ix_pose_hazard_events_track_id", "pose_hazard_events", ["track_id"])

    # ── proximity_alerts ──────────────────────────────────────
    op.create_table(
        "proximity_alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("person_track_id", sa.Integer, nullable=False),
        sa.Column("machine_track_id", sa.Integer, nullable=False),
        sa.Column("machine_class", sa.String(64), nullable=True),
        sa.Column("pixel_distance", sa.Float, nullable=True),
        sa.Column("real_distance_m", sa.Float, nullable=True),
        sa.Column("alert_level", sa.String(16), nullable=False, server_default="WARNING"),
        sa.Column("zone_id", sa.String(64), nullable=True),
        sa.Column("camera_id", sa.String(64), nullable=True),
        sa.Column("frame_idx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_proximity_alerts_timestamp", "proximity_alerts", ["timestamp"])

    # ── fire_hazard_events ────────────────────────────────────
    op.create_table(
        "fire_hazard_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("hazard_type", sa.String(32), nullable=False, server_default="fire"),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("zone_id", sa.String(64), nullable=True),
        sa.Column("camera_id", sa.String(64), nullable=True),
        sa.Column("bbox_x1", sa.Float, nullable=True),
        sa.Column("bbox_y1", sa.Float, nullable=True),
        sa.Column("bbox_x2", sa.Float, nullable=True),
        sa.Column("bbox_y2", sa.Float, nullable=True),
        sa.Column("frame_idx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("alert_sent", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_fire_hazard_events_timestamp", "fire_hazard_events", ["timestamp"])

    # ── weekly_reports ────────────────────────────────────────
    op.create_table(
        "weekly_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.String(64), nullable=True),
        sa.Column("report_date", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("site_score", sa.Float, nullable=True),
        sa.Column("total_violations", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pdf_path", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ── api_keys ──────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key_id", sa.String(64), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_api_keys_key_id", "api_keys", ["key_id"])


def downgrade() -> None:
    """Drop all tables in reverse creation order."""
    tables = [
        "api_keys", "weekly_reports", "fire_hazard_events",
        "proximity_alerts", "pose_hazard_events", "shifts", "sites",
        "model_deployments", "webhooks", "audit_log", "incident_reports",
        "agent_runs", "camera_zones", "camera_registry",
        "worker_violations", "worker_profiles", "violation_events",
    ]
    for table in tables:
        op.drop_table(table)
