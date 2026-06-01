"""CTO Review runner.

Triggered when feature enters REVIEW. For each task in PR_OPEN status,
fetches the PR diff, sends to Claude with the review system prompt, then:
  - approve → posts comment on PR, merges, marks task MERGED
  - request_changes → posts comment, sets task back to PENDING, saves
    actionable_feedback in feature.context for the dev agent next round

After all PR_OPEN tasks are processed:
  - If every task is MERGED → transition DEV_DEPLOYED → kicks off cto_deploy.
  - Otherwise → transition CODING → dev runner re-runs PENDING tasks.
"""
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
from core.enums import FeatureState, TaskStatus, TaskType
from core.orchestrator import dispatch, register_agent
from core.state_machine import transition
from integrations.anthropic_client import call_llm
from integrations.github import list_pr_files, merge_pr, post_pr_comment
from services.codebase import (
    codebase_tool_executor, get_codebase_tools_spec, refresh_snapshot,
)
from services.features import get_feature, update_context
from services.skills import load_skills_for
from services.tasks import all_tasks_in_status, list_tasks, update_task_status


REPO_BY_TYPE = {
    TaskType.BACKEND:         "github_repo_backend",
    TaskType.FRONTEND_WEB:    "github_repo_pwa",
    TaskType.FRONTEND_MOBILE: "github_repo_mobile",
}

TECH_FILE_BY_TYPE = {
    TaskType.BACKEND:         "tech/BACKEND_STACK.md",
    TaskType.FRONTEND_WEB:    "tech/PWA_STACK.md",
    TaskType.FRONTEND_MOBILE: "tech/MOBILE_STACK.md",
}


@register_agent(FeatureState.REVIEW)
async def run_cto_review(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    settings = get_settings()
    feature = await get_feature(pool, feature_id)
    if feature is None:
        return

    chat = feature.telegram_chat_id
    thread = feature.telegram_thread_id

    all_tasks = await list_tasks(pool, feature_id)
    pr_tasks = [t for t in all_tasks if t.status == TaskStatus.PR_OPEN and t.github_pr_number]

    if not pr_tasks:
        # All already-merged or nothing to review — possible if we're resumed mid-flow.
        if await all_tasks_in_status(pool, feature_id, TaskStatus.MERGED):
            await transition(pool, feature_id, FeatureState.DEV_DEPLOYED,
                             actor="agent:cto_review", reason="all tasks already merged on resume")
            await dispatch(feature_id, FeatureState.DEV_DEPLOYED, bots, pool)
        else:
            logger.warning("REVIEW entered with no PR_OPEN tasks for feature {}", feature_id)
            await transition(pool, feature_id, FeatureState.BLOCKED,
                             actor="agent:cto_review", reason="no PR_OPEN tasks to review")
        return

    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text=f"🔍 Ревьюю {len(pr_tasks)} PR…",
    )

    api_contract = feature.context.get("api_contract", {})

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

    base_review_prompt = load_prompt("cto_review")
    skills_block = ""
    if settings.skills_enabled:
        skills_md = load_skills_for("cto_review")
        if skills_md:
            skills_block = (
                "\n\n## Available skills\n\n"
                "You have the following skills available. "
                "Apply them when relevant to the task.\n\n"
                + skills_md
            )
    review_prompt = base_review_prompt + skills_block

    any_changes_requested = False

    for task in pr_tasks:
        repo_ref = getattr(settings, REPO_BY_TYPE[task.type])
        try:
            verdict_data = await _review_one_pr(
                pool=pool,
                feature_id=feature_id,
                task=task,
                repo_ref=repo_ref,
                api_contract=api_contract,
                review_prompt=review_prompt,
                model=settings.model_cto_review,
                codebase_tools=codebase_tools,
                codebase_executor=executor,
            )
        except Exception as e:
            logger.exception("Review failed for task {}: {}", task.id, e)
            await bots.cto.send_message(
                chat_id=chat, message_thread_id=thread,
                text=f"⛔ Не смог отревьюить <b>{task.title}</b>: <code>{type(e).__name__}: {e}</code>",
                parse_mode="HTML",
            )
            await update_task_status(pool, task.id, TaskStatus.BLOCKED)
            any_changes_requested = True
            continue

        verdict = verdict_data.get("verdict", "request_changes")
        summary = verdict_data.get("summary", "")
        actionable = verdict_data.get("actionable_feedback", "")
        ds_violations = verdict_data.get("design_system_violations") or []

        pr_comment_body = _format_pr_comment(
            verdict=verdict,
            summary=summary,
            actionable_feedback=actionable,
            ds_violations=ds_violations,
        )

        # Always post the review as a PR comment (visible to humans on GitHub).
        try:
            await post_pr_comment(repo_ref, task.github_pr_number, pr_comment_body)
        except Exception as e:
            logger.warning("Failed to post PR comment for #{}: {}", task.github_pr_number, e)

        if verdict == "approve":
            merged_ok = False
            try:
                merged_ok = await merge_pr(repo_ref, task.github_pr_number,
                                           method=settings.github_merge_method)
            except Exception as e:
                logger.exception("Merge failed for PR #{}: {}", task.github_pr_number, e)

            if merged_ok:
                await update_task_status(pool, task.id, TaskStatus.MERGED)
                await bots.cto.send_message(
                    chat_id=chat, message_thread_id=thread,
                    text=f"✅ Принял и смерджил: <b>{task.title}</b>\n<i>{summary}</i>",
                    parse_mode="HTML",
                )
            else:
                # Approved but couldn't merge (conflicts, branch protection, etc.)
                await bots.cto.send_message(
                    chat_id=chat, message_thread_id=thread,
                    text=(
                        f"⚠️ Одобрил <b>{task.title}</b>, но мердж не прошёл "
                        f"(конфликты или защита ветки). PR #{task.github_pr_number} ждёт твою руку."
                    ),
                    parse_mode="HTML",
                )
                # Keep task as PR_OPEN so the user can see it's still pending merge
                any_changes_requested = True

        else:
            # request_changes — save feedback into feature.context, set task back to PENDING
            feedback_key = f"review_feedback_{task.id}"
            await update_context(pool, feature_id, **{feedback_key: actionable or summary})

            await update_task_status(pool, task.id, TaskStatus.PENDING)
            await bots.cto.send_message(
                chat_id=chat, message_thread_id=thread,
                text=(
                    f"📝 Возвращаю на доработку: <b>{task.title}</b>\n"
                    f"<i>{summary}</i>\n\n"
                    f"Передаю обратно dev-агенту."
                ),
                parse_mode="HTML",
            )
            any_changes_requested = True

    # ─── Decide next state ───
    if await all_tasks_in_status(pool, feature_id, TaskStatus.MERGED):
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text="✅ Все PR смерджены. Запускаю dev-деплой.",
        )
        await transition(pool, feature_id, FeatureState.DEV_DEPLOYED,
                         actor="agent:cto_review", reason="all PRs approved + merged")
        await dispatch(feature_id, FeatureState.DEV_DEPLOYED, bots, pool)
        return

    if any_changes_requested:
        await transition(pool, feature_id, FeatureState.CODING,
                         actor="agent:cto_review", reason="changes requested on ≥1 PR")
        await dispatch(feature_id, FeatureState.CODING, bots, pool)
        return

    # All tasks are PR_OPEN (none merged due to merge failures) and no changes requested
    # → blocked, needs human
    await transition(pool, feature_id, FeatureState.BLOCKED,
                     actor="agent:cto_review",
                     reason="approved but merges failed — manual intervention needed")


async def _review_one_pr(
    *,
    pool: asyncpg.Pool,
    feature_id: UUID,
    task,
    repo_ref: str,
    api_contract: dict,
    review_prompt: str,
    model: str,
    codebase_tools: list[dict] | None = None,
    codebase_executor=None,
) -> dict:
    """Fetch PR diff, ask Claude for verdict, return parsed JSON."""
    pr_files = await list_pr_files(repo_ref, task.github_pr_number)

    # Build the diff text. Cap each file's patch to avoid massive prompts.
    MAX_PATCH_CHARS = 8000
    diff_chunks: list[str] = []
    for f in pr_files:
        path = f.get("filename", "?")
        status = f.get("status", "modified")
        patch = f.get("patch") or "(no patch — binary or empty)"
        if len(patch) > MAX_PATCH_CHARS:
            patch = patch[:MAX_PATCH_CHARS] + "\n…[truncated]"
        diff_chunks.append(f"### {path} ({status})\n```diff\n{patch}\n```")
    diff_text = "\n\n".join(diff_chunks) if diff_chunks else "(no file changes)"

    # Build the user message
    tech_md = load_context_files(TECH_FILE_BY_TYPE[task.type])
    design_md = load_context_files("DESIGN_SYSTEM.md") if task.type != TaskType.BACKEND else ""

    contract_text = ""
    if api_contract.get("summary") or api_contract.get("openapi_diff"):
        contract_text = (
            f"## API contract (authoritative)\n\n"
            f"{api_contract.get('summary', '')}\n\n"
            f"{api_contract.get('openapi_diff', '')}"
        )

    user_msg = (
        f"# Task being reviewed\n\n"
        f"**Type:** {task.type.value}\n"
        f"**Title:** {task.title}\n\n"
        f"**Description:**\n{task.description}\n\n"
        f"---\n\n"
        f"{contract_text}\n\n"
        f"---\n\n"
        f"# Stack conventions\n\n{tech_md}\n\n"
    )
    if design_md:
        user_msg += f"---\n\n# Design system\n\n{design_md}\n\n"
    user_msg += f"---\n\n# PR diff\n\n{diff_text}\n"

    raw = await call_llm(
        pool=pool,
        feature_id=feature_id,
        agent="cto_review",
        model=model,
        system=review_prompt,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=4000,
        task_id=task.id,
        tools=codebase_tools,
        tool_executor=codebase_executor,
    )

    verdict = _parse_json_safely(raw)
    if verdict is None:
        # Fall back to safe default: request changes with the raw text as feedback
        logger.warning("CTO review returned non-JSON; defaulting to request_changes")
        verdict = {
            "verdict": "request_changes",
            "summary": "CTO output не распарсился, безопасно требую доработку.",
            "actionable_feedback": raw[:2000],
            "design_system_violations": [],
        }
    return verdict


def _parse_json_safely(raw: str) -> dict | None:
    raw = raw.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _format_pr_comment(*, verdict: str, summary: str,
                      actionable_feedback: str, ds_violations: list[str]) -> str:
    icon = "✅" if verdict == "approve" else "📝"
    body = [f"## {icon} CTO review: {verdict.replace('_', ' ')}", "", summary, ""]

    if ds_violations:
        body.extend(["### Design system violations", ""])
        body.extend(f"- {v}" for v in ds_violations)
        body.append("")

    if verdict == "request_changes" and actionable_feedback:
        body.extend(["### Required changes", "", actionable_feedback, ""])

    body.append("---")
    body.append("_Posted by moy-kosmetolog-ai-team CTO agent._")
    return "\n".join(body)
