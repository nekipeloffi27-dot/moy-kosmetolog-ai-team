"""Add clarification state and clarification_history column.

Revision ID: 0002_clarification
Revises: 0001_initial
Create Date: 2026-06-01
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0002_clarification"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TYPE feature_state ADD VALUE IF NOT EXISTS 'clarification' BEFORE 'design_pending';
        """
    )
    op.execute(
        """
        ALTER TABLE features
            ADD COLUMN IF NOT EXISTS clarification_history JSONB NOT NULL DEFAULT '[]'::jsonb;
        """
    )


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values; column can be dropped.
    op.execute("ALTER TABLE features DROP COLUMN IF EXISTS clarification_history;")
    # Enum value removal requires manual migration on downgrade.
