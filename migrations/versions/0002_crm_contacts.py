"""Persist authorized CRM contacts."""

from alembic import op
import sqlalchemy as sa

revision = "0002_crm_contacts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_contacts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("contact_id", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=240), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("company_name", sa.String(length=240), nullable=True),
        sa.Column("company_domain", sa.String(length=255), nullable=True),
        sa.Column("job_title", sa.String(length=240), nullable=True),
        sa.Column("location", sa.String(length=240), nullable=True),
        sa.Column("relationship_strength", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "source_id", "contact_id"),
    )
    op.create_index("ix_crm_contacts_workspace_id", "crm_contacts", ["workspace_id"])
    op.create_index("ix_crm_contacts_source_id", "crm_contacts", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_crm_contacts_source_id", table_name="crm_contacts")
    op.drop_index("ix_crm_contacts_workspace_id", table_name="crm_contacts")
    op.drop_table("crm_contacts")
