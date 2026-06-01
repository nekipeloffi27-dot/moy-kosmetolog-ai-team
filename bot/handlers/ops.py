"""CTO operational diagnostics handlers.

/cto_diag <description>  — start a diagnostics session (creates a DIAGNOSTICS feature)
/apply_fix               — confirm and apply the proposed shell fix (FIX_PROPOSED → APPLYING_FIX)
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from loguru import logger

from core.bots import BotRegistry
from core.config import get_settings
from core.db import get_pool
from core.enums import FeatureState
from core.orchestrator import dispatch
from core.state_machine import IllegalTransition, transition
from services.features import create_feature, get_feature_by_thread, update_context
from services.threads import create_feature_topic, post_to_thread


router = Router(name="ops")


@router.message(Command("cto_diag"))
async def cmd_cto_diag(message: Message, command: CommandObject, bots: BotRegistry) -> None:
    """Open a CTO diagnostics session for a production/staging incident."""
    settings = get_settings()
    description = (command.args or "").strip()

    if not description:
        await message.answer(
            "Использование: <code>/cto_diag описание проблемы</code>\n\n"
            "Пример: <code>/cto_diag CI падает на шаге миграций с 18:00</code>",
            parse_mode="HTML",
        )
        return

    if settings.telegram_feature_group_id == 0:
        await message.answer(
            "❌ Не настроен TELEGRAM_FEATURE_GROUP_ID. "
            "Создай супергруппу с topics, добавь ботов как админов, запусти /chatid.",
            parse_mode="HTML",
        )
        return

    pool = get_pool()
    user_id = message.from_user.id if message.from_user else 0
    short_id = uuid4().hex[:6]
    title = description[:60] + ("…" if len(description) > 60 else "")

    thread_id = await create_feature_topic(
        bots.pm,
        chat_id=settings.telegram_feature_group_id,
        feature_title=f"🔧 diag · {title}",
        feature_short_id=short_id,
    )

    feature = await create_feature(
        pool,
        title=f"[diag] {title}",
        description=description,
        telegram_chat_id=settings.telegram_feature_group_id,
        telegram_thread_id=thread_id,
        telegram_user_id=user_id,
        budget_cap_cents=settings.default_budget_cap_cents,
        state=FeatureState.DIAGNOSTICS,
        initial_context={"is_diagnostics": True},
    )

    await message.answer(
        f"🔧 Сессия диагностики открыта.\n"
        f"ID: <code>{feature.id}</code>\n\n"
        f"Открой тред в группе — CTO уже анализирует.",
        parse_mode="HTML",
    )

    intro = (
        f"🔧 <b>Диагностика</b>\n\n"
        f"<i>{description}</i>\n\n"
        f"CTO запустил анализ CI, логов и состояния серверов…"
    )
    await post_to_thread(
        bots.pm,
        chat_id=settings.telegram_feature_group_id,
        thread_id=thread_id,
        text=intro,
    )

    await dispatch(feature.id, FeatureState.DIAGNOSTICS, bots, pool)


@router.message(Command("apply_fix"))
async def cmd_apply_fix(message: Message, bots: BotRegistry) -> None:
    """Apply the proposed shell fix from the CTO diagnostics session."""
    settings = get_settings()
    pool = get_pool()

    feature = await get_feature_by_thread(pool, message.chat.id, message.message_thread_id or 0)
    if feature is None:
        await message.answer("В этом треде нет привязанной диагностики.")
        return
    if feature.state != FeatureState.FIX_PROPOSED:
        await message.answer(
            "Команда работает только когда CTO предложил shell-фикс (fix_proposed)."
        )
        return

    proposed_fix: dict = feature.context.get("proposed_fix", {})
    command_str: str = proposed_fix.get("details", "").strip()
    risk_level: str = proposed_fix.get("risk_level", "medium")

    if not command_str:
        await message.answer("Нет команды для применения (details пустой в proposed_fix).")
        return

    risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk_level, "⚪")
    await message.answer(
        f"⚙️ Применяю фикс {risk_icon} ({risk_level} риск):\n"
        f"<pre>{command_str}</pre>",
        parse_mode="HTML",
    )

    try:
        await transition(pool, feature.id, FeatureState.APPLYING_FIX,
                         actor="user", reason="/apply_fix confirmed")
    except IllegalTransition as e:
        await message.answer(f"Не могу перейти в applying_fix: {e}")
        return

    try:
        stdout, returncode = await _run_shell(command_str, timeout=settings.ops_apply_fix_timeout)
    except asyncio.TimeoutError:
        await message.answer(
            f"⏱ Команда не завершилась за {settings.ops_apply_fix_timeout}с — прервана.\n"
            "Проверь состояние вручную.",
        )
        await transition(pool, feature.id, FeatureState.FAILED,
                         actor="user", reason="apply_fix timeout")
        return
    except Exception as e:
        await message.answer(f"⛔ Ошибка при запуске команды: <code>{e}</code>", parse_mode="HTML")
        await transition(pool, feature.id, FeatureState.FAILED,
                         actor="user", reason=f"apply_fix error: {e}")
        return

    output_preview = stdout[:2000] + ("…[обрезано]" if len(stdout) > 2000 else "")

    if returncode == 0:
        await message.answer(
            f"✅ Фикс применён (exit 0).\n\n"
            f"<pre>{output_preview}</pre>",
            parse_mode="HTML",
        )
        await update_context(pool, feature.id,
                             fix_result={"exit_code": 0, "stdout": stdout[:4000]})
        await transition(pool, feature.id, FeatureState.DIAGNOSTICS_DONE,
                         actor="user", reason="shell fix applied successfully")
    else:
        await message.answer(
            f"⛔ Команда завершилась с ошибкой (exit {returncode}).\n\n"
            f"<pre>{output_preview}</pre>",
            parse_mode="HTML",
        )
        await update_context(pool, feature.id,
                             fix_result={"exit_code": returncode, "stdout": stdout[:4000]})
        await transition(pool, feature.id, FeatureState.FAILED,
                         actor="user", reason=f"shell fix failed: exit {returncode}")


async def _run_shell(command: str, timeout: int) -> tuple[str, int]:
    """Run a shell command; return (combined stdout+stderr, returncode)."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return stdout.decode(errors="replace"), proc.returncode or 0
