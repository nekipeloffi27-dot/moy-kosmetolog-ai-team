"""Feature state machine.

Defines which transitions are legal. Applying a transition writes to
`state_transitions` (audit log) and updates `features.state` atomically.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from loguru import logger

from core.enums import FeatureState


ALLOWED: dict[FeatureState, set[FeatureState]] = {
    FeatureState.DESIGN_PENDING: {
        FeatureState.DESIGN_REVIEW,
        FeatureState.BLOCKED,
        FeatureState.FAILED,
    },
    FeatureState.DESIGN_REVIEW: {
        FeatureState.TASKS_PENDING,      # user approves design
        FeatureState.DESIGN_PENDING,     # user asks to redo
        FeatureState.FAILED,
    },
    FeatureState.TASKS_PENDING: {
        FeatureState.CODING,
        FeatureState.BLOCKED,
        FeatureState.FAILED,
    },
    FeatureState.CODING: {
        FeatureState.REVIEW,
        FeatureState.BLOCKED,
        FeatureState.FAILED,
    },
    FeatureState.REVIEW: {
        FeatureState.DEV_DEPLOYED,       # CTO approved all PRs and merged
        FeatureState.CODING,             # CTO requested fixes for ≥1 PR
        FeatureState.BLOCKED,
        FeatureState.FAILED,
    },
    FeatureState.DEV_DEPLOYED: {
        FeatureState.TESTING,            # deploy succeeded
        FeatureState.BLOCKED,            # deploy failed
        FeatureState.FAILED,
    },
    FeatureState.TESTING: {
        FeatureState.PROD_READY,         # user approved
        FeatureState.TASKS_PENDING,      # user found problems → re-task
        FeatureState.BLOCKED,
    },
    FeatureState.PROD_READY: {
        FeatureState.PROD_DEPLOYED,
        FeatureState.BLOCKED,            # prod deploy failed
        FeatureState.FAILED,
    },
    FeatureState.PROD_DEPLOYED: set(),   # terminal
    FeatureState.BLOCKED: {              # human unblocks → resume from a sensible state
        FeatureState.DESIGN_PENDING,
        FeatureState.TASKS_PENDING,
        FeatureState.CODING,
        FeatureState.REVIEW,
        FeatureState.DEV_DEPLOYED,       # retry deploy
        FeatureState.TESTING,
        FeatureState.PROD_READY,         # retry prod deploy
        FeatureState.FAILED,
    },
    FeatureState.FAILED: set(),          # terminal
}


class IllegalTransition(Exception):
    pass


def can_transition(from_state: FeatureState, to_state: FeatureState) -> bool:
    return to_state in ALLOWED.get(from_state, set())


async def transition(
    pool: asyncpg.Pool,
    feature_id: UUID,
    to_state: FeatureState,
    actor: str,
    reason: str | None = None,
) -> FeatureState:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT state FROM features WHERE id = $1 FOR UPDATE", feature_id
            )
            if row is None:
                raise IllegalTransition(f"Feature {feature_id} not found")

            from_state = FeatureState(row["state"])
            if not can_transition(from_state, to_state):
                raise IllegalTransition(
                    f"Cannot move {feature_id} from {from_state} to {to_state}"
                )

            await conn.execute(
                """
                UPDATE features
                SET state = $1,
                    updated_at = NOW(),
                    completed_at = CASE WHEN $1::feature_state IN ('prod_deployed','failed')
                                        THEN NOW() ELSE completed_at END
                WHERE id = $2
                """,
                to_state.value,
                feature_id,
            )

            await conn.execute(
                """
                INSERT INTO state_transitions
                    (feature_id, from_state, to_state, reason, actor)
                VALUES ($1, $2, $3, $4, $5)
                """,
                feature_id, from_state.value, to_state.value, reason, actor,
            )

            logger.info(
                "Feature {} {} → {} (actor={}, reason={})",
                feature_id, from_state, to_state, actor, reason or "—",
            )
            return to_state
