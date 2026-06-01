"""Feature lifecycle handlers — registered only on the PM bot's dispatcher."""
from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from loguru import logger

from core.bots import BotRegistry
from core.config import get_settings
from core.db import get_pool
from core.enums import FEATURE_STATE_LABELS_RU, FeatureState
from core.orchestrator import dispatch
from core.state_machine import IllegalTransition, transition
from services.features import (
    create_feature, get_feature_by_thread, list_active_features, update_context,
)
from services.threads import create_feature_topic, post_to_thread


router = Router(name="feature")

SCREENSHOTS_DIR = Path("/app/mockups/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _feature_badge(context: dict) -> str:
    """Return a short badge string for feature type, or empty string."""
    if context.get("skip_design"):
        return " [ops]"
    if context.get("design_only"):
        return " [design-only]"
    return ""


async def _create_feature_common(
    message: Message,
    bots: BotRegistry,
    title: str,
    description: str,
    *,
    initial_context: dict | None = None,
    screenshot_path: str | None = None,
) -> None:
    """Shared logic for /feature, /cto_task, /design_only."""
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

    pool = get_pool()
    user_id = message.from_user.id if message.from_user else 0
    short_id = uuid4().hex[:6]

    thread_id = await create_feature_topic(
        bots.pm,
        chat_id=settings.telegram_feature_group_id,
        feature_title=title,
        feature_short_id=short_id,
    )

    ctx = initial_context or {}
    feature = await create_feature(
        pool,
        title=title,
        description=description,
        telegram_chat_id=settings.telegram_feature_group_id,
        telegram_thread_id=thread_id,
        telegram_user_id=user_id,
        screenshot_path=screenshot_path,
        budget_cap_cents=settings.default_budget_cap_cents,
        initial_context=ctx,
    )

    badge = _feature_badge(ctx)
    await message.answer(
        f"✅ Фича <b>{title}</b>{badge} создана\n"
        f"ID: <code>{feature.id}</code>\n"
        f"Бюджет: ${feature.budget_cap_cents / 100:.2f}\n\n"
        f"Открой тред в группе — вся работа пойдёт там.",
        parse_mode="HTML",
    )

    intro = (
        f"🎬 <b>{title}</b>{badge}\n\n"
        f"<i>{description}</i>\n\n"
        f"Состояние: {FEATURE_STATE_LABELS_RU[FeatureState.CLARIFICATION]}\n"
        f"Бюджет: ${feature.budget_cap_cents / 100:.2f}"
    )
    await post_to_thread(
        bots.pm,
        chat_id=settings.telegram_feature_group_id,
        thread_id=thread_id,
        text=intro,
    )

    await dispatch(feature.id, FeatureState.CLARIFICATION, bots, pool)


@router.message(Command("feature"))
async def cmd_feature(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    """Create a new feature — full pipeline (design → coding → deploy)."""
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

    await _create_feature_common(message, bots, title, description,
                                 screenshot_path=screenshot_path)


@router.message(Command("cto_task"))
async def cmd_cto_task(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    """Create a no-design task: backend, infra, migrations, bug fixes.

    After /confirmed, skips Designer and goes straight to CTO tasking.
    """
    raw = (command.args or "").strip()
    if not raw:
        await message.answer(
            "Использование: <code>/cto_task краткий заголовок | развёрнутое описание</code>\n\n"
            "Для задач без дизайна: бэкенд, миграции, инфраструктура, фиксы API.",
            parse_mode="HTML",
        )
        return

    if "|" in raw:
        title, description = (p.strip() for p in raw.split("|", 1))
    else:
        title, description = raw, "(описание не дано)"

    await _create_feature_common(message, bots, title, description,
                                 initial_context={"skip_design": True})


@router.message(Command("design_only"))
async def cmd_design_only(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    """Create a design-only task: prototype mockups without coding.

    After /approve_design, goes to DESIGN_DONE (terminal) instead of coding.
    """
    raw = (command.args or "").strip()
    if not raw:
        await message.answer(
            "Использование: <code>/design_only краткий заголовок | развёрнутое описание</code>\n\n"
            "Только дизайн и мокапы, без разработки.",
            parse_mode="HTML",
        )
        return

    if "|" in raw:
        title, description = (p.strip() for p in raw.split("|", 1))
    else:
        title, description = raw, "(описание не дано)"

    await _create_feature_common(message, bots, title, description,
                                 initial_context={"design_only": True})


@router.message(Command("confirmed"))
async def cmd_confirmed(message: Message, bots: BotRegistry) -> None:
    """Confirm clarification and advance to design or tasking."""
    pool = get_pool()
    feature = await get_feature_by_thread(pool, message.chat.id, message.message_thread_id or 0)
    if feature is None:
        await message.answer("В этом треде нет привязанной фичи.")
        return
    if feature.state != FeatureState.CLARIFICATION:
        await message.answer("Команда работает только на этапе уточнения (clarification).")
        return

    # Promote the last PM understanding to clarified_description
    understanding = feature.context.get("pm_understanding", "")
    if understanding:
        await update_context(pool, feature.id, clarified_description=understanding)

    skip_design = feature.context.get("skip_design", False)
    next_state = FeatureState.TASKS_PENDING if skip_design else FeatureState.DESIGN_PENDING

    try:
        await transition(pool, feature.id, next_state, actor="user", reason="/confirmed")
    except IllegalTransition as e:
        await message.answer(f"Не могу подтвердить: {e}")
        return

    if skip_design:
        await message.answer("Принято. CTO режет на задачи.")
        await dispatch(feature.id, FeatureState.TASKS_PENDING, bots, pool)
    else:
        await message.answer("Принято. Передаю Дизайнеру.")
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
    badge = _feature_badge(feature.context)
    await message.answer(
        f"<b>{feature.title}</b>{badge}\n"
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
        badge = _feature_badge(f.context)
        lines.append(f"• <b>{f.title}</b>{badge} — {label}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
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


# ─── /unblock and /retry ──────────────────────────────────────────────────────

_UNBLOCK_FALLBACK = FeatureState.DESIGN_PENDING


async def _last_active_state_before_blocked(
    pool: asyncpg.Pool, feature_id: UUID
) -> FeatureState:
    """Return the state the feature was in just before it entered BLOCKED or FAILED.

    Queries state_transitions for the most recent transition whose to_state is
    'blocked' or 'failed' and returns its from_state.  Falls back to
    DESIGN_PENDING if the table is unavailable or no matching row is found.
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT from_state FROM state_transitions
                WHERE feature_id = $1 AND to_state IN ('blocked', 'failed')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                feature_id,
            )
        if row is None:
            logger.warning(
                "No blocked/failed transition found for feature {}; defaulting to {}",
                feature_id, _UNBLOCK_FALLBACK,
            )
            return _UNBLOCK_FALLBACK
        return FeatureState(row["from_state"])
    except Exception as e:
        logger.warning(
            "Could not query state_transitions for feature {} ({}); defaulting to {}",
            feature_id, e, _UNBLOCK_FALLBACK,
        )
        return _UNBLOCK_FALLBACK


async def _resolve_unblock_target(
    message: Message,
    command: CommandObject,
    pool: asyncpg.Pool,
    feature_id: UUID,
) -> FeatureState | None:
    """Parse optional target_state arg; return None and reply on validation error."""
    raw = (command.args or "").strip()
    if not raw:
        return await _last_active_state_before_blocked(pool, feature_id)
    try:
        return FeatureState(raw)
    except ValueError:
        await message.answer(
            f"Неизвестное состояние: <code>{raw}</code>.\n"
            "Укажи одно из значений <code>FeatureState</code>, например: "
            "<code>design_pending</code>, <code>tasks_pending</code>, <code>coding</code>…",
            parse_mode="HTML",
        )
        return None


@router.message(Command("unblock"))
async def cmd_unblock(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    """Move a BLOCKED/FAILED feature back to an active state without dispatching an agent."""
    pool = get_pool()
    feature = await get_feature_by_thread(pool, message.chat.id, message.message_thread_id or 0)
    if feature is None:
        await message.answer("В этом треде нет привязанной фичи.")
        return

    if feature.state not in (FeatureState.BLOCKED, FeatureState.FAILED):
        label = FEATURE_STATE_LABELS_RU[feature.state]
        await message.answer(f"Фича не заблокирована. Текущее состояние: {label}")
        return

    target = await _resolve_unblock_target(message, command, pool, feature.id)
    if target is None:
        return

    try:
        await transition(pool, feature.id, target,
                         actor="user:unblock", reason="manual unblock from chat")
    except IllegalTransition as e:
        await message.answer(f"Не могу разблокировать: <code>{e}</code>", parse_mode="HTML")
        return

    label = FEATURE_STATE_LABELS_RU[target]
    await message.answer(
        f"🔓 Разблокировано. Состояние: {label}.\n"
        "Чтобы запустить агента заново — используй подходящую команду "
        "для этого состояния (<code>/redo_design</code>, <code>/redo_review</code>, и т.д.).",
        parse_mode="HTML",
    )


@router.message(Command("retry"))
async def cmd_retry(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    """Move a BLOCKED/FAILED feature back to an active state and immediately dispatch the agent."""
    pool = get_pool()
    feature = await get_feature_by_thread(pool, message.chat.id, message.message_thread_id or 0)
    if feature is None:
        await message.answer("В этом треде нет привязанной фичи.")
        return

    if feature.state not in (FeatureState.BLOCKED, FeatureState.FAILED):
        label = FEATURE_STATE_LABELS_RU[feature.state]
        await message.answer(f"Фича не заблокирована. Текущее состояние: {label}")
        return

    target = await _resolve_unblock_target(message, command, pool, feature.id)
    if target is None:
        return

    try:
        await transition(pool, feature.id, target,
                         actor="user:retry", reason="manual retry from chat")
    except IllegalTransition as e:
        await message.answer(f"Не могу перезапустить: <code>{e}</code>", parse_mode="HTML")
        return

    label = FEATURE_STATE_LABELS_RU[target]
    await message.answer(
        f"🔄 Перезапускаю с состояния: {label}.",
        parse_mode="HTML",
    )
    await dispatch(feature.id, target, bots, pool)
