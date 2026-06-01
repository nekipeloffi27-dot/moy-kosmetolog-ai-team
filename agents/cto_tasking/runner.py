"""CTO Tasking runner — posts via bots.cto."""
from __future__ import annotations

import json
import re
from uuid import UUID

import asyncpg
from loguru import logger

from pathlib import Path

from agents.base import load_context_files, load_prompt
from core.bots import BotRegistry
from core.config import get_settings
from core.enums import FeatureState, TaskType
from core.orchestrator import dispatch, register_agent
from core.state_machine import transition
from integrations.anthropic_client import call_llm
from integrations.github import create_issue
from services.codebase import (
    codebase_tool_executor, get_codebase_tools_spec, refresh_snapshot,
)
from services.features import get_feature, update_context
from services.skills import load_skills_for
from services.tasks import create_task


REPO_BY_TYPE = {
    TaskType.BACKEND:         "github_repo_backend",
    TaskType.FRONTEND_WEB:    "github_repo_pwa",
    TaskType.FRONTEND_MOBILE: "github_repo_mobile",
}


@register_agent(FeatureState.TASKS_PENDING)
async def run_cto_tasking(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    settings = get_settings()
    feature = await get_feature(pool, feature_id)
    if feature is None:
        return

    chat = feature.telegram_chat_id
    thread = feature.telegram_thread_id

    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text="📋 Раскладываю на задачи…",
    )

    # ─── Codebase snapshot ───
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

    base_prompt = load_prompt("cto_tasking") + "\n\n# Project context\n" + load_context_files(
        "PROJECT.md", "tech/BACKEND_STACK.md", "tech/PWA_STACK.md", "tech/MOBILE_STACK.md",
    )
    skills_block = ""
    if settings.skills_enabled:
        skills_md = load_skills_for("cto_tasking")
        if skills_md:
            skills_block = (
                "\n\n## Available skills\n\n"
                "You have the following skills available. "
                "Apply them when relevant to the task.\n\n"
                + skills_md
            )
    system = base_prompt + skills_block

    design_md = feature.context.get("design_markdown", "(дизайн отсутствует)")
    retest_feedback = feature.context.get("last_test_feedback")
    effective_description = feature.context.get("clarified_description") or feature.description

    user_text = (
        f"# Original request\n\n"
        f"**Title:** {feature.title}\n\n"
        f"**Description:** {effective_description}\n\n"
        f"---\n\n"
        f"# Approved Designer output\n\n{design_md}"
    )
    if retest_feedback:
        user_text += (
            f"\n\n---\n\n# Re-tasking — user found problems in dev\n\n"
            f"{retest_feedback}\n\n"
            f"Generate tasks to fix these specifically. Don't redo unaffected work."
        )

    try:
        raw = await call_llm(
            pool=pool,
            feature_id=feature_id,
            agent="cto_tasking",
            model=settings.model_cto,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            max_tokens=8000,
            tools=codebase_tools,
            tool_executor=executor,
        )
    except Exception as e:
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text=f"⛔ Не справился: <code>{e}</code>", parse_mode="HTML",
        )
        await transition(pool, feature_id, FeatureState.BLOCKED,
                         actor="agent:cto_tasking", reason=str(e))
        return

    plan = _parse_json_safely(raw)
    if plan is None:
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text="⛔ Вернул невалидный JSON. Логи в БД.",
        )
        logger.error("CTO returned non-JSON output:\n{}", raw[:2000])
        await transition(pool, feature_id, FeatureState.BLOCKED,
                         actor="agent:cto_tasking", reason="invalid JSON")
        return

    tasks_spec = plan.get("tasks", [])
    api_contract = plan.get("api_contract", {})
    warning = plan.get("warning")

    if not tasks_spec:
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text="⚠️ Не выделил ни одной задачи. Жду указаний.",
        )
        await transition(pool, feature_id, FeatureState.BLOCKED,
                         actor="agent:cto_tasking", reason="no tasks produced")
        return

    await update_context(pool, feature_id,
                        api_contract=api_contract,
                        tasking_plan=plan)

    summary_lines = ["<b>📋 План работ:</b>", ""]
    if warning:
        summary_lines.append(f"⚠️ <i>{warning}</i>\n")
    if api_contract.get("summary"):
        summary_lines.append(f"<b>API:</b> {api_contract['summary']}\n")

    for i, t in enumerate(tasks_spec, 1):
        type_label = {
            "backend": "⚙️ Backend",
            "frontend_web": "💻 PWA",
            "frontend_mobile": "📱 Mobile",
        }.get(t["type"], t["type"])
        complexity = _validated_complexity(t)
        complexity_icon = {"simple": "🟢", "medium": "🟡", "complex": "🔴"}.get(complexity, "⚪")
        model_label = _model_label_for_complexity(complexity, settings)
        file_count = len(t.get("affected_files") or [])
        file_hint = f" ({file_count} {'файл' if file_count == 1 else 'файла' if 2 <= file_count <= 4 else 'файлов'})" if file_count else ""
        summary_lines.append(
            f"{i}. {complexity_icon} {complexity} · {model_label} · {type_label} — <b>{t['title']}</b>{file_hint}"
        )
    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text="\n".join(summary_lines), parse_mode="HTML",
    )

    issue_links: list[str] = []
    for t in tasks_spec:
        try:
            task_type = TaskType(t["type"])
        except ValueError:
            logger.warning("Skipping unknown task type: {}", t.get("type"))
            continue

        repo_ref = getattr(settings, REPO_BY_TYPE[task_type])
        issue_body = _format_issue_body(
            description=t["description"],
            api_contract=api_contract,
            feature_id=str(feature_id),
        )

        issue_data: dict | None = None
        try:
            issue_data = await create_issue(
                repo=repo_ref,
                title=f"[{str(feature_id)[:6]}] {t['title']}",
                body=issue_body,
                labels=[f"ai-team:{task_type.value}"],
            )
        except Exception as e:
            logger.exception("Failed to create issue for '{}': {}", t["title"], e)

        complexity = _validated_complexity(t)
        affected = t.get("affected_files") or []
        if not affected:
            logger.warning(
                "Task '{}' has no affected_files — plan is incomplete, forcing complexity=complex",
                t["title"],
            )
            complexity = "complex"

        await create_task(
            pool,
            feature_id=feature_id,
            type_=task_type,
            title=t["title"],
            description=t["description"],
            github_issue_number=issue_data["number"] if issue_data else None,
            complexity=complexity,
            affected_files=affected,
            changes_per_file=t.get("changes_per_file") or [],
            do_not_touch=t.get("do_not_touch") or [],
            references=t.get("references") or [],
            verification=t.get("verification"),
            expected_diff_size=t.get("expected_diff_size"),
        )

        if issue_data:
            issue_links.append(f'• <a href="{issue_data["html_url"]}">#{issue_data["number"]}</a> — {t["title"]}')

    if issue_links:
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text="<b>Issues созданы:</b>\n" + "\n".join(issue_links),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    await transition(pool, feature_id, FeatureState.CODING,
                     actor="agent:cto_tasking",
                     reason=f"{len(tasks_spec)} tasks created")

    await dispatch(feature_id, FeatureState.CODING, bots, pool)


def _model_label_for_complexity(complexity: str, settings) -> str:
    routing = {
        "simple":  settings.model_dev_simple,
        "medium":  settings.model_dev_medium,
        "complex": settings.model_dev_complex,
    }
    full = routing.get(complexity, settings.model_dev_medium)
    # Show short human-readable label: haiku/sonnet/opus
    if "haiku" in full:
        return "Haiku"
    if "sonnet" in full:
        return "Sonnet"
    if "opus" in full:
        return "Opus"
    return full


def _validated_complexity(task_spec: dict) -> str:
    value = task_spec.get("complexity", "medium")
    if value not in {"simple", "medium", "complex"}:
        logger.warning(
            "Invalid complexity '{}' for task '{}' — defaulting to medium",
            value, task_spec.get("title", "?"),
        )
        return "medium"
    return value


def _parse_json_safely(raw: str) -> dict | None:
    raw = raw.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failed: {}", e)
        return None


def _format_issue_body(*, description: str, api_contract: dict, feature_id: str) -> str:
    parts = [description, "", "---", "", "## API contract (authoritative)", ""]
    if api_contract.get("summary"):
        parts.extend([api_contract["summary"], ""])
    if api_contract.get("openapi_diff"):
        parts.append(api_contract["openapi_diff"])
    parts.extend([
        "",
        "---",
        f"_Generated by moy-kosmetolog-ai-team for feature `{feature_id}`._",
    ])
    return "\n".join(parts)
