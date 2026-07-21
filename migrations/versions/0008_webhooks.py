"""Persist signed workspace webhook subscriptions."""

from alembic import op
import sqlalchemy as sa

revision = "0008_webhooks"
down_revision = "0007_crm_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("events_json", sa.JSON(), nullable=False),
        sa.Column("secret_enc", sa.String(length=10000), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_subscriptions_workspace_id", "webhook_subscriptions", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_subscriptions_workspace_id", table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")
