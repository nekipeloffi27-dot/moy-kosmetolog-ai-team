"""Feature CRUD."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from core.enums import FeatureState
from core.models import Feature


async def create_feature(
    pool: asyncpg.Pool,
    *,
    title: str,
    description: str,
    telegram_chat_id: int,
    telegram_thread_id: int,
    telegram_user_id: int,
    screenshot_path: str | None = None,
    budget_cap_cents: int = 500,
    state: FeatureState = FeatureState.CLARIFICATION,
    initial_context: dict | None = None,
) -> Feature:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO features (
                title, description, screenshot_path,
                telegram_chat_id, telegram_thread_id, telegram_user_id,
                budget_cap_cents, state, context
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            title, description, screenshot_path,
            telegram_chat_id, telegram_thread_id, telegram_user_id,
            budget_cap_cents, state.value,
            json.dumps(initial_context or {}),
        )
    return _row_to_feature(row)


async def get_feature(pool: asyncpg.Pool, feature_id: UUID) -> Feature | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM features WHERE id = $1", feature_id)
    return _row_to_feature(row) if row else None


async def get_feature_by_thread(
    pool: asyncpg.Pool, chat_id: int, thread_id: int
) -> Feature | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM features WHERE telegram_chat_id = $1 AND telegram_thread_id = $2",
            chat_id, thread_id,
        )
    return _row_to_feature(row) if row else None


async def list_active_features(
    pool: asyncpg.Pool, user_id: int | None = None, limit: int = 50
) -> list[Feature]:
    query = """
        SELECT * FROM features
        WHERE state NOT IN ('prod_deployed', 'failed', 'design_done', 'diagnostics_done')
        {user_filter}
        ORDER BY updated_at DESC
        LIMIT $1
    """
    if user_id is not None:
        query = query.format(user_filter="AND telegram_user_id = $2")
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, limit, user_id)
    else:
        query = query.format(user_filter="")
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
    return [_row_to_feature(r) for r in rows]


async def update_context(
    pool: asyncpg.Pool, feature_id: UUID, **updates: Any
) -> None:
    """Merge into the JSONB context. Top-level keys only."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE features
            SET context = context || $1::jsonb,
                updated_at = NOW()
            WHERE id = $2
            """,
            json.dumps(updates),
            feature_id,
        )


async def append_clarification_history(
    pool: asyncpg.Pool, feature_id: UUID, entry: dict
) -> None:
    """Append one entry to clarification_history array."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE features
            SET clarification_history = clarification_history || $1::jsonb,
                updated_at = NOW()
            WHERE id = $2
            """,
            json.dumps([entry]),
            feature_id,
        )


async def add_budget_used(pool: asyncpg.Pool, feature_id: UUID, cents: int) -> int:
    """Add to budget_used_cents, return new total."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            UPDATE features
            SET budget_used_cents = budget_used_cents + $1,
                updated_at = NOW()
            WHERE id = $2
            RETURNING budget_used_cents
            """,
            cents, feature_id,
        )


async def is_over_budget(pool: asyncpg.Pool, feature_id: UUID) -> bool:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT budget_used_cents >= budget_cap_cents FROM features WHERE id = $1",
            feature_id,
        )


def _row_to_feature(row) -> Feature:
    d = dict(row)
    for jsonb_field in ("context", "clarification_history"):
        if isinstance(d.get(jsonb_field), str):
            d[jsonb_field] = json.loads(d[jsonb_field])
    return Feature(**d)
