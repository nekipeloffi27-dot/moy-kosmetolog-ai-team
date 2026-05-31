"""Designer agent runner.

Invoked when a feature is in DESIGN_PENDING. Posts via bots.designer so the
designer has its own avatar in the chat. Meta messages (kick-off / final
action prompt) come from bots.pm — the coordinator.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from aiogram.types import FSInputFile
from loguru import logger

from agents.base import load_context_files, load_prompt
from agents.designer.render import render_all_mockups
from core.bots import BotRegistry
from core.config import get_settings
from core.enums import FeatureState
from core.orchestrator import register_agent
from core.state_machine import transition
from integrations.anthropic_client import call_llm, image_block_from_path
from services.features import get_feature, update_context


@register_agent(FeatureState.DESIGN_PENDING)
async def run_designer(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    settings = get_settings()
    feature = await get_feature(pool, feature_id)
    if feature is None:
        logger.error("Designer called for missing feature {}", feature_id)
        return

    chat = feature.telegram_chat_id
    thread = feature.telegram_thread_id

    await bots.designer.send_message(
        chat_id=chat, message_thread_id=thread,
        text="🎨 Думаю над дизайном…",
    )

    # ─── Build system prompt ───
    system = load_prompt("designer") + "\n\n# Project context\n" + load_context_files(
        "PROJECT.md", "DESIGN_SYSTEM.md", "MOODBOARD.md", "ANTI_REFERENCES.md",
        "tech/PWA_STACK.md", "tech/MOBILE_STACK.md",
    )

    # ─── User message ───
    feedback = feature.context.get("design_feedback")
    user_content: list[dict[str, Any]] = []

    if feature.screenshot_path and Path(feature.screenshot_path).exists():
        user_content.append(image_block_from_path(feature.screenshot_path))

    text = f"Фича: **{feature.title}**\n\n{feature.description}"
    if feedback:
        text += (
            f"\n\n---\n\n**Замечания по предыдущей версии (от пользователя):**\n"
            f"{feedback}\n\nУчти их и предложи новый вариант."
        )
    user_content.append({"type": "text", "text": text})

    # ─── LLM call ───
    try:
        markdown_output = await call_llm(
            pool=pool,
            feature_id=feature_id,
            agent="designer",
            model=settings.model_designer,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=12_000,
        )
    except Exception as e:
        await bots.designer.send_message(
            chat_id=chat, message_thread_id=thread,
            text=f"⛔ Не справился: <code>{type(e).__name__}: {e}</code>",
            parse_mode="HTML",
        )
        await transition(pool, feature_id, FeatureState.BLOCKED,
                         actor="agent:designer", reason=str(e))
        return

    # ─── Save text output to feature context ───
    await update_context(pool, feature_id, design_markdown=markdown_output)

    # ─── Send the markdown summary (sans HTML mockups) ───
    summary = _strip_html_blocks(markdown_output)
    MAX = 4000
    for chunk_start in range(0, len(summary), MAX):
        await bots.designer.send_message(
            chat_id=chat, message_thread_id=thread,
            text=summary[chunk_start:chunk_start + MAX],
        )

    # ─── Render mockups and send as photos ───
    try:
        rendered = await render_all_mockups(markdown_output)
    except Exception as e:
        logger.exception("Render failed: {}", e)
        rendered = {}

    surface_labels = {"web": "💻 PWA / Web", "mobile": "📱 Мобилка", "landing": "🌐 Лендинг"}
    for surface, png_path in rendered.items():
        try:
            await bots.designer.send_photo(
                chat_id=chat, message_thread_id=thread,
                photo=FSInputFile(str(png_path)),
                caption=surface_labels.get(surface, surface),
            )
        except Exception as e:
            logger.exception("Failed to send mockup photo: {}", e)

    # ─── PM posts the action prompt — coordinator-style decision UI ───
    await bots.pm.send_message(
        chat_id=chat, message_thread_id=thread,
        text=(
            "Что дальше? Ответь:\n"
            "<code>/approve_design</code> — нравится, режем на задачи\n"
            "<code>/redo_design что переделать</code> — переделать с замечаниями"
        ),
        parse_mode="HTML",
    )

    await transition(pool, feature_id, FeatureState.DESIGN_REVIEW,
                     actor="agent:designer", reason="design produced")


def _strip_html_blocks(md: str) -> str:
    """Remove fenced HTML blocks from the markdown summary."""
    out_lines = []
    in_html = False
    for line in md.split("\n"):
        if line.strip().startswith("```html"):
            in_html = True
            out_lines.append("`[см. картинку ниже]`")
            continue
        if in_html:
            if line.strip() == "```":
                in_html = False
            continue
        out_lines.append(line)
    return "\n".join(out_lines)
