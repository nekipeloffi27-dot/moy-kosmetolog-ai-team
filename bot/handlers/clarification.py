"""Clarification stage message handler.

During CLARIFICATION state, any non-command text message from the user in a
feature thread is treated as a clarification reply. It gets saved to
clarification_history, then after a 5-second debounce the PM agent is re-run
so it can update its understanding.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from aiogram import F, Router
from aiogram.types import Message
from loguru import logger

from core.bots import BotRegistry
from core.db import get_pool
from core.enums import FeatureState
from core.orchestrator import dispatch
from services.features import append_clarification_history, get_feature_by_thread


router = Router(name="clarification")

# Debounce tasks: feature_id → asyncio.Task
_debounce_tasks: dict[UUID, asyncio.Task] = {}


async def _pm_rerun(feature_id: UUID, bots: BotRegistry, pool) -> None:
    await asyncio.sleep(5)
    logger.info("Debounce expired — re-running PM for feature {}", feature_id)
    await dispatch(feature_id, FeatureState.CLARIFICATION, bots, pool)


@router.message(F.text & ~F.text.startswith("/") & F.message_thread_id)
async def handle_clarification_reply(message: Message, bots: BotRegistry) -> None:
    pool = get_pool()
    thread_id = message.message_thread_id
    if thread_id is None:
        return

    feature = await get_feature_by_thread(pool, message.chat.id, thread_id)
    if feature is None or feature.state != FeatureState.CLARIFICATION:
        return

    text = (message.text or "").strip()
    if len(text) <= 5:
        return

    # Save user message to clarification history
    entry = {
        "role": "user",
        "text": text,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await append_clarification_history(pool, feature.id, entry)
    logger.info("Saved clarification reply for feature {}: {!r}", feature.id, text[:80])

    # Acknowledge receipt
    await message.reply(
        "Записал. Когда напишешь всё что нужно — <code>/confirmed</code> "
        "чтобы передать дальше, или жди — PM обновит понимание через несколько секунд.",
        parse_mode="HTML",
    )

    # Debounce: cancel previous timer, start new 5-second countdown
    existing = _debounce_tasks.get(feature.id)
    if existing and not existing.done():
        existing.cancel()
    _debounce_tasks[feature.id] = asyncio.create_task(
        _pm_rerun(feature.id, bots, pool)
    )
