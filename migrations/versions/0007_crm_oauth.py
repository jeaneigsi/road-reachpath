"""Persist CRM OAuth state and encrypted workspace connections."""

from alembic import op
import sqlalchemy as sa

revision = "0007_crm_oauth"
down_revision = "0006_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_oauth_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_crm_oauth_states_workspace_id", "crm_oauth_states", ["workspace_id"])
    op.create_index("ix_crm_oauth_states_provider", "crm_oauth_states", ["provider"])
    op.create_index("ix_crm_oauth_states_expires_at", "crm_oauth_states", ["expires_at"])

    op.create_table(
        "crm_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("api_domain", sa.String(length=255), nullable=True),
        sa.Column("scope", sa.String(length=2000), nullable=True),
        sa.Column("access_token_enc", sa.String(length=10000), nullable=False),
        sa.Column("refresh_token_enc", sa.String(length=10000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "provider"),
    )
    op.create_index("ix_crm_connections_workspace_id", "crm_connections", ["workspace_id"])
    op.create_index("ix_crm_connections_provider", "crm_connections", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_crm_connections_provider", table_name="crm_connections")
    op.drop_index("ix_crm_connections_workspace_id", table_name="crm_connections")
    op.drop_table("crm_connections")
    op.drop_index("ix_crm_oauth_states_expires_at", table_name="crm_oauth_states")
    op.drop_index("ix_crm_oauth_states_provider", table_name="crm_oauth_states")
    op.drop_index("ix_crm_oauth_states_workspace_id", table_name="crm_oauth_states")
    op.drop_table("crm_oauth_states")
