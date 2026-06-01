"""Add design_done terminal state.

Revision ID: 0003_design_done
Revises: 0002_clarification
Create Date: 2026-06-01
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0003_design_done"
down_revision: Union[str, None] = "0002_clarification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE feature_state ADD VALUE IF NOT EXISTS 'design_done';"
    )


def downgrade() -> None:
    # Enum value removal is not supported in PostgreSQL without recreating the type.
    pass
