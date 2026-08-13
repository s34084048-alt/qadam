"""diabetic foot risk assessments

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "foot_risk_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("foot", sa.String(16), nullable=False),
        sa.Column("lops", sa.String(16), nullable=False),
        sa.Column("pad", sa.String(16), nullable=False),
        sa.Column("deformity", sa.String(16), nullable=False),
        sa.Column("previous_ulcer", sa.String(16), nullable=False),
        sa.Column("previous_amputation", sa.String(16), nullable=False),
        sa.Column("end_stage_renal_disease", sa.String(16), nullable=False),
        sa.Column("category", sa.Integer(), nullable=True),
        sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("screening_interval", sa.String(128), nullable=False),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_foot_risk_case_id", "foot_risk_assessments", ["case_id"])
    op.create_index("ix_foot_risk_category", "foot_risk_assessments", ["category"])
    op.create_index("ix_foot_risk_complete", "foot_risk_assessments", ["complete"])
    op.create_index("ix_foot_risk_grade", "foot_risk_assessments", ["grade"])


def downgrade() -> None:
    op.drop_table("foot_risk_assessments")
