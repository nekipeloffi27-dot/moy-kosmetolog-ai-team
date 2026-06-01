"""Thread text handler — captures user messages during active feature states.

- CLARIFICATION : saved to clarification_history; PM re-runs after 5 s debounce.
- DESIGN_REVIEW : saved to context.design_feedback_notes; /redo_design uses them.
- REVIEW/CODING : saved to context.review_feedback_notes; /redo_review uses them.
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
from services.features import (
    append_clarification_history, append_to_context_list, get_feature_by_thread,
)


router = Router(name="clarification")

# Debounce tasks: feature_id → asyncio.Task (CLARIFICATION only)
_debounce_tasks: dict[UUID, asyncio.Task] = {}


async def _pm_rerun(feature_id: UUID, bots: BotRegistry, pool) -> None:
    await asyncio.sleep(5)
    logger.info("Debounce expired — re-running PM for feature {}", feature_id)
    await dispatch(feature_id, FeatureState.CLARIFICATION, bots, pool)


@router.message(F.text & ~F.text.startswith("/") & F.message_thread_id)
async def handle_thread_text(message: Message, bots: BotRegistry) -> None:
    pool = get_pool()
    thread_id = message.message_thread_id
    if thread_id is None:
        return

    feature = await get_feature_by_thread(pool, message.chat.id, thread_id)
    if feature is None:
        return

    text = (message.text or "").strip()
    if len(text) <= 5:
        return

    ts = datetime.now(timezone.utc).isoformat()

    # ─── CLARIFICATION ───────────────────────────────────────────────────────
    if feature.state == FeatureState.CLARIFICATION:
        entry = {"role": "user", "text": text, "ts": ts}
        await append_clarification_history(pool, feature.id, entry)
        logger.info("Clarification reply for feature {}: {!r}", feature.id, text[:80])

        await message.reply(
            "Записал. Когда напишешь всё что нужно — <code>/confirmed</code> "
            "чтобы передать дальше, или жди — PM обновит понимание через несколько секунд.",
            parse_mode="HTML",
        )

        existing = _debounce_tasks.get(feature.id)
        if existing and not existing.done():
            existing.cancel()
        _debounce_tasks[feature.id] = asyncio.create_task(
            _pm_rerun(feature.id, bots, pool)
        )

    # ─── DESIGN_REVIEW ───────────────────────────────────────────────────────
    elif feature.state == FeatureState.DESIGN_REVIEW:
        entry = {"text": text, "ts": ts}
        await append_to_context_list(pool, feature.id, "design_feedback_notes", entry)
        logger.info("Design feedback note for feature {}: {!r}", feature.id, text[:80])

        await message.reply(
            "Записал замечание. Пиши все что нужно, потом "
            "<code>/redo_design</code> — передам Дизайнеру с накопленными замечаниями.",
            parse_mode="HTML",
        )

    # ─── REVIEW / CODING ─────────────────────────────────────────────────────
    elif feature.state in (FeatureState.REVIEW, FeatureState.CODING):
        entry = {"text": text, "ts": ts}
        await append_to_context_list(pool, feature.id, "review_feedback_notes", entry)
        logger.info("Review feedback note for feature {}: {!r}", feature.id, text[:80])

        await message.reply(
            "Записал. После ревью — <code>/redo_review</code> запустит повторное "
            "CTO-ревью с твоими заметками.",
            parse_mode="HTML",
        )
