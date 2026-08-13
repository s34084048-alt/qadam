"""lab panels and results

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lab_panels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("panel_name", sa.String(128), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("age_at_collection", sa.Integer(), nullable=True),
        sa.Column("sex_used", sa.String(16), nullable=True),
        sa.Column("triage_grade", sa.String(16), nullable=False),
        sa.Column("triage_label", sa.String(128), nullable=False),
        sa.Column("next_investigation", sa.Text(), nullable=False),
        sa.Column("interpretation_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lab_panels_case_id", "lab_panels", ["case_id"])
    op.create_index("ix_lab_panels_triage_grade", "lab_panels", ["triage_grade"])

    op.create_table(
        "lab_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("panel_id", sa.Uuid(), sa.ForeignKey("lab_panels.id"),
                  nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("submitted_value", sa.Float(), nullable=False),
        sa.Column("submitted_unit", sa.String(24), nullable=False),
        sa.Column("flag", sa.String(16), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("ref_low", sa.Float(), nullable=True),
        sa.Column("ref_high", sa.Float(), nullable=True),
    )
    op.create_index("ix_lab_results_panel_id", "lab_results", ["panel_id"])
    op.create_index("ix_lab_results_code", "lab_results", ["code"])
    op.create_index("ix_lab_results_flag", "lab_results", ["flag"])


def downgrade() -> None:
    op.drop_table("lab_results")
    op.drop_table("lab_panels")
