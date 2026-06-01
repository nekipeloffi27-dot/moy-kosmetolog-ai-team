"""Add revert pipeline states.

Revision ID: 0005_revert
Revises: 0004_diagnostics
Create Date: 2026-06-01
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0005_revert"
down_revision: Union[str, None] = "0004_diagnostics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for value in ("reverting", "reverted"):
        op.execute(f"ALTER TYPE feature_state ADD VALUE IF NOT EXISTS '{value}';")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
