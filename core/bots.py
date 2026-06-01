"""Bot registry — holds all 5 Telegram bot instances.

Architecture:
- `pm` is the only bot with a polling loop. It receives every command.
- The other four bots have no Dispatcher — they only POST into threads,
  giving each agent its own avatar/name in the chat.

This module is the only place that knows how many bots exist.
"""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from loguru import logger

from core.config import Settings
from core.enums import TaskType


@dataclass
class BotRegistry:
    pm: Bot           # project manager — listens + coordinates
    designer: Bot     # posts design output
    cto: Bot          # posts CTO output (tasking, review, deploy)
    backend: Bot      # posts backend dev output
    frontend: Bot     # posts frontend (web + mobile) dev output

    def for_task_type(self, task_type: TaskType) -> Bot:
        """Return the worker bot that should post for a given task type."""
        return {
            TaskType.BACKEND:         self.backend,
            TaskType.FRONTEND_WEB:    self.frontend,
            TaskType.FRONTEND_MOBILE: self.frontend,
        }[task_type]

    def all(self) -> list[Bot]:
        return [self.pm, self.designer, self.cto, self.backend, self.frontend]

    async def close(self) -> None:
        """Close all HTTP sessions cleanly."""
        for bot in self.all():
            try:
                await bot.session.close()
            except Exception as e:
                logger.warning("Failed to close session for bot {}: {}", bot.id or "?", e)


_bots: "BotRegistry | None" = None


def set_bots(registry: "BotRegistry") -> None:
    global _bots
    _bots = registry


def get_bots() -> "BotRegistry":
    if _bots is None:
        raise RuntimeError("BotRegistry not initialized — call set_bots() at startup")
    return _bots


async def init_bots(settings: Settings) -> BotRegistry:
    """Construct all 5 bots and verify each token is valid by calling getMe."""
    defaults = DefaultBotProperties(parse_mode=None)

    registry = BotRegistry(
        pm       = Bot(token=settings.telegram_pm_bot_token,       default=defaults),
        designer = Bot(token=settings.telegram_designer_bot_token, default=defaults),
        cto      = Bot(token=settings.telegram_cto_bot_token,      default=defaults),
        backend  = Bot(token=settings.telegram_backend_bot_token,  default=defaults),
        frontend = Bot(token=settings.telegram_frontend_bot_token, default=defaults),
    )

    # Sanity check: each token must produce a successful getMe.
    for role, bot in [
        ("pm", registry.pm),
        ("designer", registry.designer),
        ("cto", registry.cto),
        ("backend", registry.backend),
        ("frontend", registry.frontend),
    ]:
        me = await bot.get_me()
        logger.info("Bot [{}] connected: @{} (id={})", role, me.username, me.id)

    return registry
