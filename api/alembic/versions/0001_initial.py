"""initial QADAM schema

Revision ID: 0001
Revises:
Create Date: 2026-08-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="clinician"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "patients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("external_ref", sa.String(64), nullable=False),
        sa.Column("dob_year", sa.Integer(), nullable=True),
        sa.Column("sex", sa.String(16), nullable=True),
        sa.Column("skin_tone_monk", sa.Integer(), nullable=True),
        sa.Column("consent_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_patients_external_ref", "patients", ["external_ref"], unique=True)

    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("body_site", sa.String(64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_cases_patient_id", "cases", ["patient_id"])
    op.create_index("ix_cases_module", "cases", ["module"])
    op.create_index("ix_cases_status", "cases", ["status"])

    op.create_table(
        "images",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False,
                  server_default="image/jpeg"),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_images_case_id", "images", ["case_id"])

    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("image_id", sa.Uuid(), sa.ForeignKey("images.id"), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("backend", sa.String(32), nullable=False,
                  server_default="classical_cv"),
        sa.Column("triage_grade", sa.String(16), nullable=False),
        sa.Column("triage_label", sa.String(128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("next_investigation", sa.Text(), nullable=False),
        sa.Column("rationale_json", sa.JSON(), nullable=False),
        sa.Column("overlay_key", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analyses_case_id", "analyses", ["case_id"])
    op.create_index("ix_analyses_image_id", "analyses", ["image_id"])
    op.create_index("ix_analyses_module", "analyses", ["module"])
    op.create_index("ix_analyses_triage_grade", "analyses", ["triage_grade"])

    op.create_table(
        "lesions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("area_pct", sa.Float(), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("bbox_json", sa.JSON(), nullable=False),
        sa.Column("centroid_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_lesions_analysis_id", "lesions", ["analysis_id"])

    op.create_table(
        "model_registry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("backend", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("artifact_uri", sa.String(512), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_registry_module", "model_registry", ["module"])
    op.create_index("ix_model_registry_module_active", "model_registry",
                    ["module", "active"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_log_actor_user_id", "audit_log", ["actor_user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])

    # audit_log is append-only. On PostgreSQL this is enforced at the database
    # level so no application bug -- and no future contributor -- can rewrite
    # the trail. Other dialects rely on the application-level guarantee.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION qadam_audit_append_only()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_log is append-only';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER qadam_audit_no_update_delete
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION qadam_audit_append_only();
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS qadam_audit_no_update_delete ON audit_log;")
        op.execute("DROP FUNCTION IF EXISTS qadam_audit_append_only();")
    op.drop_table("audit_log")
    op.drop_table("model_registry")
    op.drop_table("lesions")
    op.drop_table("analyses")
    op.drop_table("images")
    op.drop_table("cases")
    op.drop_table("patients")
    op.drop_table("users")
