"""CTO Ops diagnostics runner.

Triggered when a feature enters DIAGNOSTICS state (via /cto_diag).
Uses read-only ops tools (GitHub Actions, docker logs, SSH) to investigate,
then proposes a fix. Posts findings to the feature thread via bots.cto.

Fix types:
  shell  → transition FIX_PROPOSED; /apply_fix will execute the command.
  pr     → transition DIAGNOSTICS_DONE; human picks up via normal pipeline.
  manual → transition DIAGNOSTICS_DONE; human must act directly.
"""
from __future__ import annotations

import json
import re
from uuid import UUID

import asyncpg
from loguru import logger

from agents.base import load_prompt
from core.bots import BotRegistry
from core.config import get_settings
from core.enums import FeatureState
from core.orchestrator import dispatch, register_agent
from core.state_machine import transition
from integrations.anthropic_client import call_llm
from services.features import get_feature, update_context
from services.ops_tools import get_ops_tools_spec, ops_tool_executor
from services.skills import load_skills_for


@register_agent(FeatureState.DIAGNOSTICS)
async def run_cto_ops(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    settings = get_settings()
    feature = await get_feature(pool, feature_id)
    if feature is None:
        logger.error("CTO ops called for missing feature {}", feature_id)
        return

    chat = feature.telegram_chat_id
    thread = feature.telegram_thread_id

    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text="🔧 CTO изучает проблему — запрашиваю логи CI, Docker и сервера…",
    )

    # ─── System prompt ───
    base_prompt = load_prompt("cto_ops")
    skills_block = ""
    if settings.skills_enabled:
        skills_md = load_skills_for("cto_ops")
        if skills_md:
            skills_block = (
                "\n\n## Available skills\n\n"
                "You have the following skills available. "
                "Apply them when relevant to the task.\n\n"
                + skills_md
            )
    system = base_prompt + skills_block

    # ─── User message ───
    user_msg = (
        f"# Incident report\n\n"
        f"**Description:** {feature.description}\n\n"
        "Investigate the issue using the available tools, then respond with a "
        "single JSON object as described in your system prompt."
    )

    ops_tools = get_ops_tools_spec()

    try:
        raw = await call_llm(
            pool=pool,
            feature_id=feature_id,
            agent="cto_ops",
            model=settings.model_cto,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=4000,
            tools=ops_tools,
            tool_executor=ops_tool_executor,
            max_tool_iterations=15,
        )
    except Exception as e:
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text=f"⛔ CTO ops не смог завершить диагностику: <code>{type(e).__name__}: {e}</code>",
            parse_mode="HTML",
        )
        logger.exception("CTO ops failed for feature {}: {}", feature_id, e)
        await transition(pool, feature_id, FeatureState.FAILED,
                         actor="agent:cto_ops", reason=f"LLM error: {e}")
        return

    result = _parse_json(raw)
    if result is None:
        logger.error("CTO ops returned non-JSON:\n{}", raw[:2000])
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text=(
                "⛔ CTO вернул некорректный ответ.\n\n"
                f"<pre>{raw[:3000]}</pre>"
            ),
            parse_mode="HTML",
        )
        await transition(pool, feature_id, FeatureState.FAILED,
                         actor="agent:cto_ops", reason="non-JSON response")
        return

    summary = result.get("summary", "")
    findings: list[str] = result.get("findings", [])
    hypothesis = result.get("hypothesis", "")
    proposed_fix: dict = result.get("proposed_fix", {})
    fix_type = proposed_fix.get("type", "manual")
    fix_details = proposed_fix.get("details", "")
    risk_level = proposed_fix.get("risk_level", "medium")

    # ─── Save to context ───
    await update_context(pool, feature_id, proposed_fix=proposed_fix,
                         ops_summary=summary, ops_hypothesis=hypothesis)

    # ─── Post findings ───
    findings_text = ""
    if findings:
        findings_text = "\n".join(f"• {f}" for f in findings)

    risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk_level, "⚪")

    fix_type_label = {
        "shell": "🖥 Shell-команда",
        "pr":    "📋 Pull Request",
        "manual": "👷 Ручное действие",
    }.get(fix_type, fix_type)

    msg = (
        f"<b>🔧 Диагностика завершена</b>\n\n"
        f"<b>Резюме:</b> {summary}\n\n"
    )
    if findings_text:
        msg += f"<b>Находки:</b>\n{findings_text}\n\n"
    msg += (
        f"<b>Гипотеза:</b> {hypothesis}\n\n"
        f"<b>Тип фикса:</b> {fix_type_label} {risk_icon} ({risk_level} риск)\n"
        f"<b>Детали:</b>\n<pre>{fix_details}</pre>"
    )

    if fix_type == "shell":
        msg += "\n\nДля применения введи <code>/apply_fix</code> в этом треде."

    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text=msg, parse_mode="HTML",
    )

    # ─── Transition ───
    if fix_type == "shell":
        await transition(pool, feature_id, FeatureState.FIX_PROPOSED,
                         actor="agent:cto_ops", reason=f"shell fix proposed ({risk_level} risk)")
    else:
        await transition(pool, feature_id, FeatureState.DIAGNOSTICS_DONE,
                         actor="agent:cto_ops", reason=f"fix type={fix_type}, no shell apply needed")

    logger.info(
        "CTO ops for feature {}: fix_type={}, risk={}",
        feature_id, fix_type, risk_level,
    )


def _parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find a bare JSON object
        m2 = re.search(r"\{.*\}", raw, re.DOTALL)
        if m2:
            try:
                return json.loads(m2.group(0))
            except json.JSONDecodeError:
                pass
        return None
