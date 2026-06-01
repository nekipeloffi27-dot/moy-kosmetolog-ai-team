"""PM Clarification agent runner.

Invoked when a feature enters CLARIFICATION state. On first run, reformulates
the feature request and asks up to 3 targeted questions. On re-runs (after user
replies in thread), re-reads the full clarification history and updates its
understanding. Posts via bots.pm.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from loguru import logger

from agents.base import load_prompt
from core.bots import BotRegistry
from core.config import get_settings
from core.enums import FeatureState
from core.orchestrator import register_agent
from integrations.anthropic_client import call_llm, image_block_from_path
from services.features import (
    append_clarification_history, get_feature, update_context,
)
from services.skills import load_skills_for


@register_agent(FeatureState.CLARIFICATION)
async def run_pm_clarification(
    feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool
) -> None:
    settings = get_settings()
    feature = await get_feature(pool, feature_id)
    if feature is None:
        logger.error("PM clarification called for missing feature {}", feature_id)
        return

    chat = feature.telegram_chat_id
    thread = feature.telegram_thread_id

    # ─── Build system prompt ───
    base_prompt = load_prompt("pm")
    skills_block = ""
    if settings.skills_enabled:
        skills_md = load_skills_for("pm")
        if skills_md:
            skills_block = (
                "\n\n## Available skills\n\n"
                "You have the following skills available. "
                "Apply them when relevant to the task.\n\n"
                + skills_md
            )
    system = base_prompt + skills_block

    # ─── Build user message ───
    is_first_run = not feature.context.get("pm_understanding")
    user_content: list[dict[str, Any]] = []

    if is_first_run and feature.screenshot_path and Path(feature.screenshot_path).exists():
        user_content.append(image_block_from_path(feature.screenshot_path))

    text = (
        f"# Feature request\n\n"
        f"**Title:** {feature.title}\n\n"
        f"**Description:** {feature.description}\n"
    )

    history = feature.clarification_history
    if history:
        text += "\n\n# Clarification history\n\n"
        for item in history:
            role_label = "User" if item.get("role") == "user" else "PM"
            text += f"**{role_label}:** {item['text']}\n\n"

    user_content.append({"type": "text", "text": text})

    # ─── LLM call ───
    try:
        raw = await call_llm(
            pool=pool,
            feature_id=feature_id,
            agent="pm_clarification",
            model=settings.model_pm,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=2000,
        )
    except Exception as e:
        await bots.pm.send_message(
            chat_id=chat, message_thread_id=thread,
            text=f"⛔ PM не справился с уточнением: <code>{type(e).__name__}: {e}</code>",
            parse_mode="HTML",
        )
        logger.exception("PM clarification failed for feature {}: {}", feature_id, e)
        return

    result = _parse_json(raw)
    if result is None:
        logger.error("PM returned non-JSON output:\n{}", raw[:2000])
        await bots.pm.send_message(
            chat_id=chat, message_thread_id=thread,
            text="⛔ PM вернул некорректный ответ. Попробуй /confirmed чтобы пропустить этап.",
        )
        return

    understanding = result.get("understanding", "")
    questions: list[str] = result.get("questions", [])

    # ─── Save to feature context ───
    await update_context(pool, feature_id,
                         pm_understanding=understanding,
                         pm_questions=questions)

    # ─── Append to clarification_history ───
    pm_entry = {
        "role": "pm",
        "text": understanding,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await append_clarification_history(pool, feature_id, pm_entry)

    # ─── Post to Telegram ───
    msg = f"<b>Я понял задачу так:</b>\n\n{understanding}"

    if questions:
        msg += "\n\n<b>Прежде чем передать дальше, уточни:</b>\n"
        for i, q in enumerate(questions, 1):
            msg += f"{i}. {q}\n"
        msg += "\nОтветь в треде, потом <code>/confirmed</code>."
    else:
        msg += "\n\nЕсли всё верно — <code>/confirmed</code>. Если нет — уточни в треде."

    await bots.pm.send_message(
        chat_id=chat, message_thread_id=thread,
        text=msg, parse_mode="HTML",
    )

    logger.info(
        "PM clarification for feature {}: ready={}, questions={}",
        feature_id, result.get("ready"), len(questions),
    )


def _parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("PM JSON parse failed: {}", e)
        return None
