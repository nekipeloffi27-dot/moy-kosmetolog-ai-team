"""Task CRUD."""
from __future__ import annotations

from uuid import UUID

import asyncpg

from core.enums import TaskStatus, TaskType
from core.models import Task


async def create_task(
    pool: asyncpg.Pool,
    *,
    feature_id: UUID,
    type_: TaskType,
    title: str,
    description: str,
    github_issue_number: int | None = None,
) -> Task:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tasks (feature_id, type, title, description, github_issue_number)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            feature_id, type_.value, title, description, github_issue_number,
        )
    return Task(**dict(row))


async def list_tasks(pool: asyncpg.Pool, feature_id: UUID) -> list[Task]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tasks WHERE feature_id = $1 ORDER BY created_at",
            feature_id,
        )
    return [Task(**dict(r)) for r in rows]


async def update_task_status(
    pool: asyncpg.Pool,
    task_id: UUID,
    status: TaskStatus,
    *,
    github_pr_number: int | None = None,
    branch_name: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE tasks
            SET status = $1,
                github_pr_number = COALESCE($2, github_pr_number),
                branch_name = COALESCE($3, branch_name),
                updated_at = NOW()
            WHERE id = $4
            """,
            status.value, github_pr_number, branch_name, task_id,
        )


async def all_tasks_in_status(
    pool: asyncpg.Pool, feature_id: UUID, status: TaskStatus
) -> bool:
    """True iff every task for the feature has the given status."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = $1) AS matching
            FROM tasks
            WHERE feature_id = $2
            """,
            status.value, feature_id,
        )
    return row["total"] > 0 and row["total"] == row["matching"]


async def all_tasks_ready_for_review(pool: asyncpg.Pool, feature_id: UUID) -> bool:
    """True iff every task is in PR_OPEN or MERGED state (i.e. nothing left to develop)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status IN ('pr_open','merged')) AS ready
            FROM tasks
            WHERE feature_id = $1
            """,
            feature_id,
        )
    return row["total"] > 0 and row["total"] == row["ready"]
