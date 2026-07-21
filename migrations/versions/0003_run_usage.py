"""Track usage metrics for research runs."""

from alembic import op
import sqlalchemy as sa

revision = "0003_run_usage"
down_revision = "0002_crm_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_runs", sa.Column("usage_json", sa.JSON(), nullable=True))
    op.execute("UPDATE research_runs SET usage_json = '{}' WHERE usage_json IS NULL")
    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.alter_column("usage_json", nullable=False)


def downgrade() -> None:
    op.drop_column("research_runs", "usage_json")
