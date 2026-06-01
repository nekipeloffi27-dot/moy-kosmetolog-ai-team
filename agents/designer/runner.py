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
from services.codebase import (
    codebase_tool_executor, get_codebase_tools_spec, refresh_snapshot,
)
from services.features import get_feature, update_context
from services.skills import load_skills_for


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

    # ─── Codebase snapshot: try to refresh, enable tools if available ───
    snapshot_dir = Path(settings.codebase_snapshot_dir)
    codebase_tools = None
    executor = None
    if snapshot_dir.exists():
        try:
            await refresh_snapshot()
        except Exception as e:
            logger.warning("Codebase snapshot refresh failed (continuing without): {}", e)
        codebase_tools = get_codebase_tools_spec()
        executor = codebase_tool_executor

    # ─── Build system prompt ───
    base_prompt = load_prompt("designer") + "\n\n# Project context\n" + load_context_files(
        "PROJECT.md", "DESIGN_SYSTEM.md", "MOODBOARD.md", "ANTI_REFERENCES.md",
        "tech/PWA_STACK.md", "tech/MOBILE_STACK.md",
    )
    skills_block = ""
    if settings.skills_enabled:
        skills_md = load_skills_for("designer")
        if skills_md:
            skills_block = (
                "\n\n## Available skills\n\n"
                "You have the following skills available. "
                "Apply them when relevant to the task.\n\n"
                + skills_md
            )
    codebase_section = ""
    if codebase_tools:
        codebase_section = (
            "\n\n## Codebase access\n\n"
            "У тебя есть инструменты для чтения текущего репозитория moy-kosmetolog:\n"
            "- `list_directory(path)` — посмотреть содержимое папки\n"
            "- `read_file(path)` — прочитать файл\n"
            "- `search_codebase(pattern, glob)` — поиск по коду\n\n"
            "Используй их ПЕРЕД генерацией мокапа:\n"
            "1. Посмотри `packages/web/components` — какие UI-компоненты (halo-ds) уже есть\n"
            "2. Посмотри `packages/web/app` — какие страницы и роуты существуют\n"
            "3. Посмотри `packages/mobile/screens` — какие экраны есть в мобилке\n\n"
            "Мокап должен опираться на существующие компоненты — не выдумывай новые "
            "имена без необходимости. Если нужного компонента нет — опиши это явно."
        )
    system = base_prompt + skills_block + codebase_section

    # ─── User message ───
    feedback = feature.context.get("design_feedback")
    user_content: list[dict[str, Any]] = []

    if feature.screenshot_path and Path(feature.screenshot_path).exists():
        user_content.append(image_block_from_path(feature.screenshot_path))

    effective_description = feature.context.get("clarified_description") or feature.description
    text = f"Фича: **{feature.title}**\n\n{effective_description}"
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
            tools=codebase_tools,
            tool_executor=executor,
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
            "Что дальше?\n\n"
            "<code>/approve_design</code> — нравится, режем на задачи\n"
            "<code>/redo_design</code> — переделать\n\n"
            "<i>Замечания можно писать прямо в треде — накапливаются автоматически. "
            "Потом <code>/redo_design</code> без аргументов.</i>"
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
