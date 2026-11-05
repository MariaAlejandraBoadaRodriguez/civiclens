"""Job progress: the running phase and a 0–100 percentage, polled by the web app.

Revision ID: 002
Revises: 001
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("phase", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("progress", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("progress")
        batch.drop_column("phase")
