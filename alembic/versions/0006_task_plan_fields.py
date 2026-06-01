"""Add execution plan fields to tasks table.

Revision ID: 0006_task_plan_fields
Revises: 0005_revert
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006_task_plan_fields"
down_revision: Union[str, None] = "0005_revert"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column(
        "complexity",
        sa.String(16),
        nullable=False,
        server_default="medium",
    ))
    op.add_column("tasks", sa.Column(
        "affected_files",
        sa.dialects.postgresql.JSONB(),
        nullable=False,
        server_default="'[]'",
    ))
    op.add_column("tasks", sa.Column(
        "changes_per_file",
        sa.dialects.postgresql.JSONB(),
        nullable=False,
        server_default="'[]'",
    ))
    op.add_column("tasks", sa.Column(
        "do_not_touch",
        sa.dialects.postgresql.JSONB(),
        nullable=False,
        server_default="'[]'",
    ))
    op.add_column("tasks", sa.Column(
        "references",
        sa.dialects.postgresql.JSONB(),
        nullable=False,
        server_default="'[]'",
    ))
    op.add_column("tasks", sa.Column(
        "verification",
        sa.Text(),
        nullable=True,
    ))
    op.add_column("tasks", sa.Column(
        "expected_diff_size",
        sa.String(32),
        nullable=True,
    ))


def downgrade() -> None:
    op.drop_column("tasks", "expected_diff_size")
    op.drop_column("tasks", "verification")
    op.drop_column("tasks", "references")
    op.drop_column("tasks", "do_not_touch")
    op.drop_column("tasks", "changes_per_file")
    op.drop_column("tasks", "affected_files")
    op.drop_column("tasks", "complexity")
