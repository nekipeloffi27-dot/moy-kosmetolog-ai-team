"""Admin / utility handlers."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.db import health_check


router = Router(name="admin")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 Привет! Команда AI-агентов на связи.\n\n"
        "<b>Основные команды:</b>\n"
        "/feature — создать фичу (с текстом и опц. скриншотом)\n"
        "/status — статус фичи в этом треде\n"
        "/list — мои активные фичи\n"
        "/cancel — отменить фичу в этом треде\n\n"
        "<b>Утилиты:</b>\n"
        "/chatid — узнать ID чата/треда/юзера\n"
        "/ping — проверка БД\n"
        "/version — версия сборки",
        parse_mode="HTML",
    )


@router.message(Command("chatid"))
async def cmd_chatid(message: Message) -> None:
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    user_id = message.from_user.id if message.from_user else None
    await message.answer(
        f"<b>chat_id:</b> <code>{chat_id}</code>\n"
        f"<b>thread_id:</b> <code>{thread_id}</code>\n"
        f"<b>your user_id:</b> <code>{user_id}</code>",
        parse_mode="HTML",
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    ok = await health_check()
    await message.answer("✅ БД отвечает" if ok else "❌ БД не отвечает — проверь логи")


@router.message(Command("version"))
async def cmd_version(message: Message) -> None:
    await message.answer(
        "<b>moy-kosmetolog-ai-team</b>\nMilestone: M1–M5 (full pipeline)",
        parse_mode="HTML",
    )
