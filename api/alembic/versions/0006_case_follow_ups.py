"""clinician follow-up answers

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-13

Additive only. No existing table is altered and no existing row is touched, so
a clinic upgrading mid-clinic keeps every case exactly as it was.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_follow_ups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analyses.id"),
                  nullable=True),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("image_grade", sa.String(16), nullable=False),
        sa.Column("answer_grade", sa.String(16), nullable=False),
        sa.Column("combined_grade", sa.String(16), nullable=False),
        sa.Column("escalated", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("answers_json", sa.JSON(), nullable=False),
        sa.Column("outcome_json", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_case_follow_ups_case_id", "case_follow_ups", ["case_id"])
    op.create_index("ix_case_follow_ups_analysis_id", "case_follow_ups",
                    ["analysis_id"])
    op.create_index("ix_case_follow_ups_module", "case_follow_ups", ["module"])
    op.create_index("ix_case_follow_ups_image_grade", "case_follow_ups",
                    ["image_grade"])
    op.create_index("ix_case_follow_ups_answer_grade", "case_follow_ups",
                    ["answer_grade"])
    op.create_index("ix_case_follow_ups_combined_grade", "case_follow_ups",
                    ["combined_grade"])
    op.create_index("ix_case_follow_ups_escalated", "case_follow_ups",
                    ["escalated"])


def downgrade() -> None:
    for name in ("escalated", "combined_grade", "answer_grade", "image_grade",
                 "module", "analysis_id", "case_id"):
        op.drop_index(f"ix_case_follow_ups_{name}", table_name="case_follow_ups")
    op.drop_table("case_follow_ups")
