"""Add diagnostics pipeline states.

Revision ID: 0004_diagnostics
Revises: 0003_design_done
Create Date: 2026-06-01
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0004_diagnostics"
down_revision: Union[str, None] = "0003_design_done"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for value in ("diagnostics", "fix_proposed", "applying_fix", "diagnostics_done"):
        op.execute(f"ALTER TYPE feature_state ADD VALUE IF NOT EXISTS '{value}';")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
