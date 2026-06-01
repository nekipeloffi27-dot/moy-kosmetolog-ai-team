"""Bot entry. Boots 5 bots; only PM polls. All handlers attached to PM's dispatcher.

The other 4 bots (designer, cto, backend, frontend) are silent — they have
their own Bot instances for posting but no Dispatcher.

Each agent runner receives the full BotRegistry via DI and picks the right
worker bot for posting.
"""
from __future__ import annotations

import asyncio
import sys

from aiogram import Dispatcher
from aiogram.types import Message
from loguru import logger

from core.bots import BotRegistry, init_bots
from core.config import get_settings
from core.db import close_pool, get_pool, init_pool
from core.orchestrator import resume_pending

from bot.handlers import admin, clarification, feature, feedback, ops

# Importing agents triggers their @register_agent decorators
import agents  # noqa: F401


def setup_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}:{function}</cyan> - <level>{message}</level>"
        ),
    )


def access_guard_middleware(allowed: set[int]):
    """aiogram outer middleware blocking non-whitelisted users (on PM bot only)."""
    from aiogram import BaseMiddleware
    from aiogram.types import TelegramObject

    class Guard(BaseMiddleware):
        async def __call__(self, handler, event: TelegramObject, data: dict):
            if isinstance(event, Message):
                text = (event.text or event.caption or "")
                if text.startswith("/chatid"):
                    return await handler(event, data)
                uid = event.from_user.id if event.from_user else None
                if allowed and uid not in allowed:
                    logger.warning("Blocked message from non-whitelisted user {}", uid)
                    return
                if not allowed:
                    logger.warning("Whitelist empty — bot is OPEN! Set TELEGRAM_ALLOWED_USER_IDS")
            return await handler(event, data)

    return Guard()


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info("Booting moy-kosmetolog-ai-team (multi-bot mode)")
    logger.info("Allowed users: {}", settings.allowed_user_ids or "OPEN")
    logger.info("Feature group: {}", settings.telegram_feature_group_id or "NOT SET")

    await init_pool()
    pool = get_pool()

    bots: BotRegistry = await init_bots(settings)

    dp = Dispatcher()
    # Make the BotRegistry available to every handler as a `bots` parameter
    dp["bots"] = bots

    dp.update.outer_middleware(access_guard_middleware(settings.allowed_user_ids))

    dp.include_router(admin.router)
    dp.include_router(feature.router)
    dp.include_router(feedback.router)
    dp.include_router(clarification.router)
    dp.include_router(ops.router)

    # Resume features that were mid-flight at last shutdown
    await resume_pending(bots, pool)

    try:
        # Polling on PM only — worker bots don't listen
        await dp.start_polling(bots.pm, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bots.close()
        await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down")
