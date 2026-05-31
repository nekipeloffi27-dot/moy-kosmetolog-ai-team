"""Feature lifecycle handlers — registered only on the PM bot's dispatcher."""
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from loguru import logger

from core.bots import BotRegistry
from core.config import get_settings
from core.db import get_pool
from core.enums import FEATURE_STATE_LABELS_RU, FeatureState
from core.orchestrator import dispatch
from services.features import (
    create_feature, get_feature_by_thread, list_active_features,
)
from services.threads import create_feature_topic, post_to_thread


router = Router(name="feature")

SCREENSHOTS_DIR = Path("/app/mockups/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


@router.message(Command("feature"))
async def cmd_feature(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    """Create a new feature. Bot used: PM (for downloading photos + topic creation)."""
    settings = get_settings()
    if settings.telegram_feature_group_id == 0:
        await message.answer(
            "❌ Не настроена группа для фич. "
            "Создай супергруппу с topics, добавь всех ботов как админов, "
            "выполни <code>/chatid</code> внутри и пропиши "
            "<code>TELEGRAM_FEATURE_GROUP_ID</code> в .env",
            parse_mode="HTML",
        )
        return

    raw = command.args or message.caption or ""
    raw = re.sub(r"^/feature(@\w+)?\s*", "", raw).strip()

    if not raw:
        await message.answer(
            "Использование: <code>/feature краткий заголовок | развёрнутое описание</code>",
            parse_mode="HTML",
        )
        return

    if "|" in raw:
        title, description = (p.strip() for p in raw.split("|", 1))
    else:
        title, description = raw, "(описание не дано)"

    screenshot_path: str | None = None
    if message.photo:
        photo = message.photo[-1]
        screenshot_path = str(SCREENSHOTS_DIR / f"{uuid4().hex}.jpg")
        await bots.pm.download(photo, destination=screenshot_path)
        logger.info("Saved screenshot {} for feature '{}'", screenshot_path, title)

    pool = get_pool()
    user_id = message.from_user.id if message.from_user else 0

    short_id = uuid4().hex[:6]
    # PM creates the topic — it's the coordinator
    thread_id = await create_feature_topic(
        bots.pm,
        chat_id=settings.telegram_feature_group_id,
        feature_title=title,
        feature_short_id=short_id,
    )

    feature = await create_feature(
        pool,
        title=title,
        description=description,
        telegram_chat_id=settings.telegram_feature_group_id,
        telegram_thread_id=thread_id,
        telegram_user_id=user_id,
        screenshot_path=screenshot_path,
        budget_cap_cents=settings.default_budget_cap_cents,
    )

    await message.answer(
        f"✅ Фича <b>{title}</b> создана\n"
        f"ID: <code>{feature.id}</code>\n"
        f"Бюджет: ${feature.budget_cap_cents / 100:.2f}\n\n"
        f"Открой тред в группе — вся работа пойдёт там.",
        parse_mode="HTML",
    )

    # PM posts the feature intro
    intro = (
        f"🎬 <b>{title}</b>\n\n"
        f"<i>{description}</i>\n\n"
        f"Состояние: {FEATURE_STATE_LABELS_RU[FeatureState.DESIGN_PENDING]}\n"
        f"Бюджет: ${feature.budget_cap_cents / 100:.2f}"
    )
    await post_to_thread(
        bots.pm,
        chat_id=settings.telegram_feature_group_id,
        thread_id=thread_id,
        text=intro,
    )

    await dispatch(feature.id, FeatureState.DESIGN_PENDING, bots, pool)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    pool = get_pool()
    chat_id = message.chat.id
    thread_id = message.message_thread_id

    if thread_id is None:
        await message.answer("Команда работает только внутри треда фичи.")
        return

    feature = await get_feature_by_thread(pool, chat_id, thread_id)
    if feature is None:
        await message.answer("В этом треде нет привязанной фичи.")
        return

    label = FEATURE_STATE_LABELS_RU[feature.state]
    await message.answer(
        f"<b>{feature.title}</b>\n"
        f"Статус: {label}\n"
        f"Использовано: ${feature.budget_used_cents / 100:.2f} "
        f"из ${feature.budget_cap_cents / 100:.2f}\n"
        f"ID: <code>{feature.id}</code>",
        parse_mode="HTML",
    )


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    pool = get_pool()
    user_id = message.from_user.id if message.from_user else 0
    features = await list_active_features(pool, user_id=user_id, limit=20)

    if not features:
        await message.answer("Активных фич нет. Создай первую: /feature")
        return

    lines = ["<b>Активные фичи:</b>", ""]
    for f in features:
        label = FEATURE_STATE_LABELS_RU[f.state]
        lines.append(f"• <b>{f.title}</b> — {label}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    from core.state_machine import transition, IllegalTransition

    pool = get_pool()
    feature = await get_feature_by_thread(pool, message.chat.id, message.message_thread_id or 0)
    if feature is None:
        await message.answer("В этом треде нет фичи.")
        return

    try:
        await transition(pool, feature.id, FeatureState.FAILED,
                         actor="user", reason="manual cancel")
        await message.answer("Фича отменена.")
    except IllegalTransition as e:
        await message.answer(f"Не могу отменить: {e}")
