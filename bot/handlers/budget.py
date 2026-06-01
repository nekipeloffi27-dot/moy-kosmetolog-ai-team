"""Budget handlers: /budget (global report) and /cost (per-feature detail)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from core.db import get_pool
from services.budget_report import (
    format_feature_report,
    format_global_report,
    get_feature_report,
    get_global_report,
)
from services.features import get_feature_by_thread

router = Router(name="budget")

_VALID_PERIODS = {"today", "week", "month", "all"}


@router.message(Command("budget"))
async def cmd_budget(message: Message, command: CommandObject) -> None:
    """Global cost report. Usage: /budget [today|week|month|all]"""
    period = (command.args or "today").strip().lower()
    if period not in _VALID_PERIODS:
        await message.answer(
            "Использование: <code>/budget [today|week|month|all]</code>",
            parse_mode="HTML",
        )
        return

    pool = get_pool()
    report = await get_global_report(pool, period)
    text = format_global_report(report)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("cost"))
async def cmd_cost(message: Message) -> None:
    """Detailed cost breakdown for the current feature thread."""
    if message.message_thread_id is None:
        await message.answer("Команда работает только внутри треда фичи.")
        return

    pool = get_pool()
    feature = await get_feature_by_thread(pool, message.chat.id, message.message_thread_id)
    if feature is None:
        await message.answer("В этом треде нет привязанной фичи.")
        return

    report = await get_feature_report(pool, feature.id)
    text = format_feature_report(report)
    await message.answer(text, parse_mode="HTML")
