"""A data flow end can also name a function of the application on that end."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("source_function_id", "target_function_id"):
        op.add_column(
            "data_flow",
            sa.Column(
                column, sa.Uuid, sa.ForeignKey("function.id", ondelete="SET NULL"), nullable=True
            ),
        )


def downgrade() -> None:
    for column in ("target_function_id", "source_function_id"):
        op.drop_column("data_flow", column)
