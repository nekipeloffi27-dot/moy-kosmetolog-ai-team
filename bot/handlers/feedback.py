"""Feedback handlers — registered only on the PM bot's dispatcher."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from core.bots import BotRegistry
from core.db import get_pool
from core.enums import FeatureState
from core.orchestrator import dispatch
from core.state_machine import IllegalTransition, transition
from services.features import get_feature, get_feature_by_thread, update_context


router = Router(name="feedback")


async def _get_feature_or_none(message: Message):
    pool = get_pool()
    if message.message_thread_id is None:
        return None, pool
    feature = await get_feature_by_thread(pool, message.chat.id, message.message_thread_id)
    return feature, pool


@router.message(Command("approve_design"))
async def cmd_approve_design(message: Message, bots: BotRegistry) -> None:
    feature, pool = await _get_feature_or_none(message)
    if not feature or feature.state != FeatureState.DESIGN_REVIEW:
        await message.answer("Сейчас не на этапе ревью дизайна.")
        return

    if feature.context.get("design_only"):
        try:
            await transition(pool, feature.id, FeatureState.DESIGN_DONE,
                             actor="user", reason="design approved (design-only)")
            await bots.pm.send_message(
                chat_id=feature.telegram_chat_id,
                message_thread_id=feature.telegram_thread_id,
                text=(
                    "✅ Дизайн готов. Mockup'ы сохранены в треде.\n\n"
                    "Если нужна разработка — создай фичу через "
                    "<code>/feature</code> с тем же описанием."
                ),
                parse_mode="HTML",
            )
        except IllegalTransition as e:
            await message.answer(f"Не вышло: {e}")
    else:
        try:
            await transition(pool, feature.id, FeatureState.TASKS_PENDING,
                             actor="user", reason="design approved")
            await message.answer("Принято. CTO режет на задачи.")
            await dispatch(feature.id, FeatureState.TASKS_PENDING, bots, pool)
        except IllegalTransition as e:
            await message.answer(f"Не вышло: {e}")


@router.message(Command("redo_design"))
async def cmd_redo_design(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    feature, pool = await _get_feature_or_none(message)
    if not feature or feature.state != FeatureState.DESIGN_REVIEW:
        await message.answer("Команда работает только на этапе ревью дизайна.")
        return

    inline = (command.args or "").strip()
    notes: list[dict] = feature.context.get("design_feedback_notes", [])

    parts = [n["text"] for n in notes if n.get("text")]
    if inline:
        parts.append(inline)
    combined = "\n".join(parts) if parts else "(без комментариев)"

    # Save combined feedback; clear accumulated notes
    await update_context(pool, feature.id,
                         design_feedback=combined,
                         design_feedback_notes=[])
    try:
        await transition(pool, feature.id, FeatureState.DESIGN_PENDING,
                         actor="user", reason=f"redo: {combined[:200]}")
        await message.answer("Понял, передаю Дизайнеру с замечаниями.")
        await dispatch(feature.id, FeatureState.DESIGN_PENDING, bots, pool)
    except IllegalTransition as e:
        await message.answer(f"Не вышло: {e}")


@router.message(Command("redo_review"))
async def cmd_redo_review(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    """Re-trigger CTO code review, passing accumulated user feedback as context."""
    feature, pool = await _get_feature_or_none(message)
    if feature is None:
        await message.answer("В этом треде нет привязанной фичи.")
        return

    _VALID = {FeatureState.CODING, FeatureState.DEV_DEPLOYED, FeatureState.REVIEW}
    if feature.state not in _VALID:
        await message.answer(
            f"Команда работает из состояний: {', '.join(s.value for s in _VALID)}.\n"
            f"Сейчас: <b>{feature.state.value}</b>",
            parse_mode="HTML",
        )
        return

    inline = (command.args or "").strip()
    notes: list[dict] = feature.context.get("review_feedback_notes", [])

    parts = [n["text"] for n in notes if n.get("text")]
    if inline:
        parts.append(inline)
    user_notes = "\n".join(parts) if parts else ""

    await update_context(pool, feature.id,
                         user_review_notes=user_notes,
                         review_feedback_notes=[])

    try:
        if feature.state != FeatureState.REVIEW:
            await transition(pool, feature.id, FeatureState.REVIEW,
                             actor="user", reason="/redo_review")
        await message.answer(
            "Запускаю CTO ревью"
            + (f" с твоими заметками:\n<i>{user_notes[:400]}</i>" if user_notes else "") + ".",
            parse_mode="HTML",
        )
        await dispatch(feature.id, FeatureState.REVIEW, bots, pool)
    except IllegalTransition as e:
        await message.answer(f"Не вышло: {e}")


@router.message(Command("pass_test"))
async def cmd_pass_test(message: Message) -> None:
    feature, pool = await _get_feature_or_none(message)
    if not feature or feature.state != FeatureState.TESTING:
        await message.answer("Команда работает только на этапе тестирования.")
        return
    try:
        await transition(pool, feature.id, FeatureState.PROD_READY,
                         actor="user", reason="tests passed by user")
        await message.answer(
            "Отлично! Готово к проду.\n"
            "Чтобы выкатить — пришли /deploy_prod confirm"
        )
    except IllegalTransition as e:
        await message.answer(f"Не вышло: {e}")


@router.message(Command("fail_test"))
async def cmd_fail_test(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    feature, pool = await _get_feature_or_none(message)
    if not feature or feature.state != FeatureState.TESTING:
        await message.answer("Команда работает только на этапе тестирования.")
        return

    feedback = (command.args or "").strip()
    if not feedback:
        await message.answer(
            "Опиши что не так:\n"
            "<code>/fail_test кнопка не нажимается на мобилке, время выбирается с ошибкой</code>",
            parse_mode="HTML",
        )
        return

    await update_context(pool, feature.id, last_test_feedback=feedback)
    try:
        await transition(pool, feature.id, FeatureState.TASKS_PENDING,
                         actor="user", reason=f"test failed: {feedback[:200]}")
        await message.answer("Принял замечания. Передаю CTO — переоткроет задачи.")
        await dispatch(feature.id, FeatureState.TASKS_PENDING, bots, pool)
    except IllegalTransition as e:
        await message.answer(f"Не вышло: {e}")


@router.message(Command("deploy_prod"))
async def cmd_deploy_prod(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    feature, pool = await _get_feature_or_none(message)
    if not feature or feature.state != FeatureState.PROD_READY:
        await message.answer("Сейчас фича не готова к проду.")
        return

    arg = (command.args or "").strip()
    if arg != "confirm":
        await message.answer(
            "Для подтверждения отправь:\n<code>/deploy_prod confirm</code>",
            parse_mode="HTML",
        )
        return

    await message.answer("Запускаю прод-деплой…")
    await dispatch(feature.id, FeatureState.PROD_READY, bots, pool)
