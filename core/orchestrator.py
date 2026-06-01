"""Orchestrator: dispatches agents based on state changes.

Now receives a BotRegistry — each agent picks the right bot for posting.
"""
from __future__ import annotations

import asyncio
from uuid import UUID

import asyncpg
from loguru import logger

from core.bots import BotRegistry
from core.enums import FeatureState
from core.state_machine import transition


# Registry of agent runners. Populated by agents/__init__.py on import.
# Signature: async def runner(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None
AGENT_DISPATCH: dict[FeatureState, callable] = {}


def register_agent(state: FeatureState):
    def deco(fn):
        AGENT_DISPATCH[state] = fn
        logger.info("Registered agent for state {} → {}", state.value, fn.__name__)
        return fn
    return deco


async def dispatch(feature_id: UUID, state: FeatureState, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    runner = AGENT_DISPATCH.get(state)
    if runner is None:
        logger.debug("No agent registered for state {}", state.value)
        return

    logger.info("Dispatching agent for feature {} in state {}", feature_id, state.value)

    async def _safe_run():
        try:
            await runner(feature_id, bots, pool)
        except Exception as e:
            logger.exception("Agent run failed for feature {}: {}", feature_id, e)
            try:
                await transition(
                    pool, feature_id, FeatureState.BLOCKED,
                    actor=f"agent:{runner.__name__}",
                    reason=f"unhandled error: {e}",
                )
            except Exception:
                logger.exception("Failed to mark feature as BLOCKED")

    asyncio.create_task(_safe_run())


async def resume_pending(bots: BotRegistry, pool: asyncpg.Pool) -> None:
    """On bot startup, resume any features that were mid-agent when we last shut down."""
    states_needing_agent = [
        FeatureState.CLARIFICATION,
        FeatureState.DESIGN_PENDING,
        FeatureState.TASKS_PENDING,
        FeatureState.CODING,
        FeatureState.REVIEW,
        FeatureState.DEV_DEPLOYED,
        FeatureState.PROD_READY,
        FeatureState.DIAGNOSTICS,
        FeatureState.REVERTING,
    ]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, state FROM features WHERE state = ANY($1::feature_state[])",
            [s.value for s in states_needing_agent],
        )

    for row in rows:
        logger.info("Resuming feature {} in state {}", row["id"], row["state"])
        await dispatch(row["id"], FeatureState(row["state"]), bots, pool)
