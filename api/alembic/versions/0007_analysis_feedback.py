"""clinician feedback on an analysis

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-15

Additive only. The validation dataset starts here, one recorded disagreement
at a time.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analyses.id"),
                  nullable=False),
        sa.Column("reported_grade", sa.String(16), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(24), nullable=False),
        sa.Column("ground_truth", sa.String(32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    for col in ("case_id", "analysis_id", "reported_grade", "verdict",
                "ground_truth"):
        op.create_index(f"ix_analysis_feedback_{col}", "analysis_feedback", [col])


def downgrade() -> None:
    for col in ("ground_truth", "verdict", "reported_grade", "analysis_id",
                "case_id"):
        op.drop_index(f"ix_analysis_feedback_{col}", table_name="analysis_feedback")
    op.drop_table("analysis_feedback")
