"""organisational isolation

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-12

Existing installations hold data that predates organisations. Everything is
moved into one "Default organisation" rather than deleted or left orphaned:
a migration that loses a clinic's records is not an acceptable upgrade.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    bind = op.get_bind()

    organisations = op.create_table(
        "organisations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_organisations_slug", "organisations", ["slug"], unique=True)

    # Everything that already exists belongs to one organisation until an
    # administrator says otherwise.
    op.bulk_insert(organisations, [{
        "id": DEFAULT_ORG_ID,
        "name": "Default organisation",
        "slug": "default",
        "country": None,
        "is_active": True,
    }])

    for table in ("users", "patients", "cases"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=True))
        bind.execute(
            sa.text(f"UPDATE {table} SET organisation_id = :org"),  # noqa: S608
            {"org": str(DEFAULT_ORG_ID)},
        )
        with op.batch_alter_table(table) as batch:
            batch.alter_column("organisation_id", nullable=False)
            batch.create_foreign_key(
                f"fk_{table}_organisation", "organisations",
                ["organisation_id"], ["id"],
            )
        op.create_index(f"ix_{table}_organisation_id", table, ["organisation_id"])

    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=True))
    bind.execute(sa.text("UPDATE audit_log SET organisation_id = :org"),
                 {"org": str(DEFAULT_ORG_ID)})
    op.create_index("ix_audit_log_organisation_id", "audit_log",
                    ["organisation_id"])

    # A patient code is unique WITHIN an organisation, not globally. A global
    # unique index would let one clinic discover another's codes by collision.
    with op.batch_alter_table("patients") as batch:
        batch.drop_index("ix_patients_external_ref")
        batch.create_index("ix_patients_external_ref", ["external_ref"])
        batch.create_unique_constraint(
            "uq_patient_org_ref", ["organisation_id", "external_ref"])


def downgrade() -> None:
    with op.batch_alter_table("patients") as batch:
        batch.drop_constraint("uq_patient_org_ref", type_="unique")
        batch.drop_index("ix_patients_external_ref")
        batch.create_index("ix_patients_external_ref", ["external_ref"], unique=True)

    op.drop_index("ix_audit_log_organisation_id", table_name="audit_log")
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_column("organisation_id")

    for table in ("cases", "patients", "users"):
        op.drop_index(f"ix_{table}_organisation_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_organisation", type_="foreignkey")
            batch.drop_column("organisation_id")

    op.drop_index("ix_organisations_slug", table_name="organisations")
    op.drop_table("organisations")
