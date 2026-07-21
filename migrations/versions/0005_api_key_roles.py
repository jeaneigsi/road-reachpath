"""Add workspace API key roles."""

from alembic import op
import sqlalchemy as sa

revision = "0005_api_key_roles"
down_revision = "0004_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("role", sa.String(length=20), nullable=False, server_default="operator"),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "role")
