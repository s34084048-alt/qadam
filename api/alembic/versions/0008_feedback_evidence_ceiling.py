"""record the evidence ceiling alongside each piece of feedback

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-17

Additive and nullable. Rows written before the evidence layer existed keep
NULL, which is honest: for those the question "was the cap wrong?" has no
answer because nothing was capped.

WHY THIS IS NOT COSMETIC. The evidence layer can now LOWER a grade the measured
areas alone would have raised. That closed a reproduced false positive, and the
obvious risk of any such change is that it opens a false negative somewhere
else. These two columns are what lets the recorded disagreement answer that:

    verdict=too_low AND grade_capped=true   -> the cap was wrong (evidence.py)
    verdict=too_low AND grade_capped=false  -> the threshold was wrong

Without them both arrive as the same row and the two causes cannot be
separated in the data.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_feedback",
        sa.Column("evidence_ceiling", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "analysis_feedback",
        sa.Column("grade_capped", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_analysis_feedback_evidence_ceiling",
        "analysis_feedback", ["evidence_ceiling"],
    )
    op.create_index(
        "ix_analysis_feedback_grade_capped",
        "analysis_feedback", ["grade_capped"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_feedback_grade_capped", "analysis_feedback")
    op.drop_index("ix_analysis_feedback_evidence_ceiling", "analysis_feedback")
    op.drop_column("analysis_feedback", "grade_capped")
    op.drop_column("analysis_feedback", "evidence_ceiling")
