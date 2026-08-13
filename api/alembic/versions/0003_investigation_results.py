"""investigation results attached to a case

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("modality", sa.String(32), nullable=True),
        sa.Column("body_site", sa.String(64), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reporting_service", sa.String(128), nullable=True),
        sa.Column("report_text", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("content_type", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("identifiers_removed_ack", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_investigation_results_case_id",
                    "investigation_results", ["case_id"])
    op.create_index("ix_investigation_results_category",
                    "investigation_results", ["category"])


def downgrade() -> None:
    op.drop_table("investigation_results")
