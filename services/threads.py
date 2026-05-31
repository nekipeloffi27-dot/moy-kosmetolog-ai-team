"""Telegram supergroup topic (thread) management.

Each feature lives in its own forum topic inside the configured supergroup.
We create the topic at /feature time and post all agent output into it.
"""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import ForumTopic
from loguru import logger


async def create_feature_topic(
    bot: Bot,
    chat_id: int,
    feature_title: str,
    feature_short_id: str,
) -> int:
    """Create a new topic in the feature group, return message_thread_id."""
    name = f"{feature_short_id} · {feature_title[:50]}"
    topic: ForumTopic = await bot.create_forum_topic(
        chat_id=chat_id,
        name=name,
        icon_color=0xFB6F5F,   # warm coral
    )
    logger.info("Created topic {} (id={}) in chat {}", name, topic.message_thread_id, chat_id)
    return topic.message_thread_id


async def close_feature_topic(bot: Bot, chat_id: int, thread_id: int) -> None:
    try:
        await bot.close_forum_topic(chat_id=chat_id, message_thread_id=thread_id)
    except Exception as e:
        logger.warning("Failed to close topic {}: {}", thread_id, e)


async def post_to_thread(
    bot: Bot,
    chat_id: int,
    thread_id: int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
) -> None:
    """Send text to a feature thread. Long messages are split."""
    MAX = 4000
    for chunk in [text[i:i + MAX] for i in range(0, len(text), MAX)]:
        await bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=chunk,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
