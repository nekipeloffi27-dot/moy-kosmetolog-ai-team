"""Revert handler — /revert command.

Usage:
  /revert                — in a feature thread: revert that feature
  /revert <feature_id>   — anywhere: revert by full UUID
"""
from __future__ import annotations

from uuid import UUID

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from loguru import logger

from core.bots import BotRegistry
from core.db import get_pool
from core.enums import FeatureState
from core.orchestrator import dispatch
from core.state_machine import IllegalTransition, transition
from services.features import get_feature, get_feature_by_thread


router = Router(name="revert")

_REVERTABLE = {
    FeatureState.DEV_DEPLOYED,
    FeatureState.TESTING,
    FeatureState.PROD_READY,
    FeatureState.PROD_DEPLOYED,
    FeatureState.BLOCKED,
    FeatureState.REVIEW,
}


@router.message(Command("revert"))
async def cmd_revert(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    pool = get_pool()
    feature_id_arg = (command.args or "").strip()

    if feature_id_arg:
        try:
            fid = UUID(feature_id_arg)
        except ValueError:
            await message.answer(
                "Неверный формат ID. Используй полный UUID:\n"
                "<code>/revert xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx</code>",
                parse_mode="HTML",
            )
            return
        feature = await get_feature(pool, fid)
        if feature is None:
            await message.answer(f"Фича <code>{feature_id_arg}</code> не найдена.",
                                 parse_mode="HTML")
            return
    else:
        thread_id = message.message_thread_id
        if thread_id is None:
            await message.answer(
                "Запусти команду внутри треда фичи или укажи ID:\n"
                "<code>/revert &lt;feature_id&gt;</code>",
                parse_mode="HTML",
            )
            return
        feature = await get_feature_by_thread(pool, message.chat.id, thread_id)
        if feature is None:
            await message.answer("В этом треде нет привязанной фичи.")
            return

    if feature.state not in _REVERTABLE:
        await message.answer(
            f"Откат невозможен из состояния <b>{feature.state.value}</b>.\n"
            f"Допустимые состояния: {', '.join(s.value for s in _REVERTABLE)}",
            parse_mode="HTML",
        )
        return

    try:
        await transition(pool, feature.id, FeatureState.REVERTING,
                         actor="user", reason="/revert command")
    except IllegalTransition as e:
        await message.answer(f"Не могу начать откат: {e}")
        return

    await message.answer(
        f"⏪ Запускаю откат для <b>{feature.title}</b>.\n"
        f"CTO создаст revert PR для всех смерджённых изменений.",
        parse_mode="HTML",
    )

    logger.info("User triggered revert for feature {}", feature.id)
    await dispatch(feature.id, FeatureState.REVERTING, bots, pool)
