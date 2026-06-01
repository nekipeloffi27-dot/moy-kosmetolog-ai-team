"""Dev agent runner — spawns one Docker container per pending task.

For re-runs (after CTO review requested changes), the same task is set back
to PENDING. We inject any saved review_feedback into TASK.md so the dev
agent sees what needs fixing. The sandbox detects an existing branch and
adds commits to it, so the existing PR auto-updates.
"""
from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from uuid import UUID

import asyncpg
from aiogram import Bot
from loguru import logger

from agents.base import CONTEXT_DIR
from core.bots import BotRegistry
from core.config import get_settings
from core.enums import FeatureState, TaskStatus, TaskType
from core.orchestrator import register_agent
from core.state_machine import transition
from integrations.github import clone_url
from services.features import get_feature
from services.tasks import all_tasks_ready_for_review, list_tasks, update_task_status


AGENT_DIR_BY_TYPE = {
    TaskType.BACKEND:         "backend_dev",
    TaskType.FRONTEND_WEB:    "frontend_web_dev",
    TaskType.FRONTEND_MOBILE: "frontend_mobile_dev",
}
REPO_ATTR_BY_TYPE = {
    TaskType.BACKEND:         "github_repo_backend",
    TaskType.FRONTEND_WEB:    "github_repo_pwa",
    TaskType.FRONTEND_MOBILE: "github_repo_mobile",
}
MODEL_ATTR_BY_TYPE = {
    TaskType.BACKEND:         "model_backend_dev",
    TaskType.FRONTEND_WEB:    "model_frontend_web_dev",
    TaskType.FRONTEND_MOBILE: "model_frontend_mobile_dev",
}


@register_agent(FeatureState.CODING)
async def run_dev_agents(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    feature = await get_feature(pool, feature_id)
    if feature is None:
        return

    tasks = await list_tasks(pool, feature_id)
    pending = [t for t in tasks if t.status == TaskStatus.PENDING]
    if not pending:
        logger.info("No pending tasks for feature {}", feature_id)
        return

    label = "dev-агента" if len(pending) == 1 else "dev-агентов"
    await bots.pm.send_message(
        chat_id=feature.telegram_chat_id,
        message_thread_id=feature.telegram_thread_id,
        text=f"⌨️ Запускаю {len(pending)} {label} параллельно…",
    )

    results = await asyncio.gather(
        *[_run_one_task(t, feature, pool, bots) for t in pending],
        return_exceptions=True,
    )

    failed = [r for r in results if isinstance(r, Exception)]
    if failed:
        for f in failed:
            logger.error("Dev task crashed: {}", f)
        await bots.pm.send_message(
            chat_id=feature.telegram_chat_id,
            message_thread_id=feature.telegram_thread_id,
            text=f"⚠️ Часть dev-агентов упала ({len(failed)} из {len(results)}). Перехожу в BLOCKED.",
        )
        await transition(pool, feature_id, FeatureState.BLOCKED,
                         actor="agent:dev", reason="one or more dev agents failed")
        return

    if await all_tasks_ready_for_review(pool, feature_id):
        await bots.pm.send_message(
            chat_id=feature.telegram_chat_id,
            message_thread_id=feature.telegram_thread_id,
            text="✅ Все таски в PR. Передаю CTO на ревью.",
        )
        await transition(pool, feature_id, FeatureState.REVIEW,
                         actor="agent:dev", reason="all tasks ready for review")
        from core.orchestrator import dispatch
        await dispatch(feature_id, FeatureState.REVIEW, bots, pool)
    else:
        await bots.pm.send_message(
            chat_id=feature.telegram_chat_id,
            message_thread_id=feature.telegram_thread_id,
            text="⚠️ Не все таски дошли до PR. Смотри статусы тасок и логи sandbox.",
        )
        await transition(pool, feature_id, FeatureState.BLOCKED,
                         actor="agent:dev", reason="not all tasks reached pr_open")


async def _run_one_task(task, feature, pool: asyncpg.Pool, bots: BotRegistry) -> None:
    settings = get_settings()
    worker_bot: Bot = bots.for_task_type(task.type)

    agent_dir = AGENT_DIR_BY_TYPE[task.type]
    repo_ref = getattr(settings, REPO_ATTR_BY_TYPE[task.type])
    model = getattr(settings, MODEL_ATTR_BY_TYPE[task.type])
    repo, subdir = settings.parse_repo(repo_ref)
    full_repo = f"{settings.github_owner}/{repo}"

    short_id = str(feature.id)[:6]
    # Deterministic branch name — re-runs reuse the same branch and update the PR
    branch = task.branch_name or f"feat/{short_id}/{_slugify(task.title)}"
    container_name = f"dev-{short_id}-{task.type.value}-{str(task.id)[:8]}"

    await update_task_status(pool, task.id, TaskStatus.IN_PROGRESS, branch_name=branch)

    # Decide tone of the start message — re-run vs. first run
    is_rerun = bool(feature.context.get(f"review_feedback_{task.id}"))
    start_text = (
        f"♻️ Возвращаюсь к таске после ревью: <b>{task.title}</b>\n"
        f"Branch: <code>{branch}</code>"
        if is_rerun else
        f"🚧 Старт: <b>{task.title}</b>\n"
        f"Branch: <code>{branch}</code>"
    )
    await worker_bot.send_message(
        chat_id=feature.telegram_chat_id,
        message_thread_id=feature.telegram_thread_id,
        text=start_text, parse_mode="HTML",
    )

    clone_url_str = await clone_url(repo_ref)
    api_contract = feature.context.get("api_contract", {})
    design_md = feature.context.get("design_markdown", "")
    test_feedback = feature.context.get("last_test_feedback", "")
    review_feedback = feature.context.get(f"review_feedback_{task.id}", "")

    prompts_dir = Path(settings.sandbox_workspace) / "prompts" / str(feature.id) / task.type.value
    work_dir = Path(settings.sandbox_workspace) / "work" / str(feature.id) / task.type.value
    for d in (
        prompts_dir.parent.parent, prompts_dir.parent, prompts_dir,
        work_dir.parent.parent, work_dir.parent, work_dir,
    ):
        _ensure_writable(d)

    task_md = (
        f"# {task.title}\n\n"
        f"{task.description}\n\n"
        f"---\n\n## Authoritative API contract\n\n"
        f"{api_contract.get('openapi_diff', '(no API changes)')}\n\n"
        f"---\n\n## Designer output (reference)\n\n{design_md}\n"
    )
    if review_feedback:
        task_md += (
            f"\n\n---\n\n## CTO review feedback (from previous round)\n\n"
            f"{review_feedback}\n\n"
            f"**This branch already has commits. Add commits to fix the issues above. "
            f"Don't redo anything that wasn't called out.**\n"
        )
    if test_feedback:
        task_md += f"\n\n## User-test feedback from previous dev round\n\n{test_feedback}\n"

    (prompts_dir / "TASK.md").write_text(task_md, encoding="utf-8")

    agent_root = Path(__file__).parent.parent / agent_dir
    claude_md = (agent_root / "CLAUDE.md").read_text(encoding="utf-8")
    system_prompt = (agent_root / "system_prompt.md").read_text(encoding="utf-8")

    tech_file = {
        TaskType.BACKEND: "BACKEND_STACK.md",
        TaskType.FRONTEND_WEB: "PWA_STACK.md",
        TaskType.FRONTEND_MOBILE: "MOBILE_STACK.md",
    }[task.type]
    project_md = (CONTEXT_DIR / "PROJECT.md").read_text(encoding="utf-8")
    design_system = (CONTEXT_DIR / "DESIGN_SYSTEM.md").read_text(encoding="utf-8")
    tech_md = (CONTEXT_DIR / "tech" / tech_file).read_text(encoding="utf-8")

    full_claude_md = (
        f"{claude_md}\n\n"
        f"---\n\n# Project context (PROJECT.md)\n\n{project_md}\n\n"
        f"---\n\n# Design system (DESIGN_SYSTEM.md)\n\n{design_system}\n\n"
        f"---\n\n# Tech stack ({tech_file})\n\n{tech_md}\n"
    )
    (prompts_dir / "CLAUDE.md").write_text(full_claude_md, encoding="utf-8")
    (prompts_dir / "AGENT_SYSTEM_PROMPT.md").write_text(system_prompt, encoding="utf-8")

    docker_cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--network", "ai-team-net",
        "-e", f"REPO_URL={clone_url_str}",
        "-e", f"REPO_NAME={repo}",
        "-e", f"REPO_FULL={full_repo}",
        "-e", f"REPO_SUBDIR={subdir}",
        "-e", f"BRANCH={branch}",
        "-e", f"DEFAULT_BRANCH={settings.github_default_branch}",
        "-e", f"ANTHROPIC_API_KEY={settings.anthropic_api_key}",
        "-e", f"ANTHROPIC_PROXY_URL={settings.anthropic_proxy_url}",
        "-e", f"MODEL={model}",
        "-e", f"GH_TOKEN={settings.github_token}",
        "-e", f"TASK_TITLE={task.title}",
        "-e", f"PR_TITLE=[{short_id}] {task.title}",
        "-e", f"ISSUE_NUMBER={task.github_issue_number or ''}",
        "-e", f"IS_RERUN={'1' if is_rerun else '0'}",
        "-v", f"{prompts_dir}:/prompts:ro",
        "-v", f"{work_dir}:/workspace",
    ]

    if settings.skills_enabled:
        skills_root = Path(settings.skills_dir)
        common_skills = skills_root / "common"
        role_skills = skills_root / task.type.value
        if common_skills.exists():
            docker_cmd += ["-v", f"{common_skills}:/root/.claude/skills/common:ro"]
        if role_skills.exists():
            docker_cmd += ["-v", f"{role_skills}:/root/.claude/skills/{task.type.value}:ro"]

    docker_cmd.append(settings.dev_sandbox_image)

    logger.info("Spawning sandbox: {}", " ".join(shlex.quote(p) for p in docker_cmd))

    proc = await asyncio.create_subprocess_exec(
        *docker_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=settings.dev_agent_timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await asyncio.create_subprocess_exec("docker", "kill", container_name)
        await update_task_status(pool, task.id, TaskStatus.BLOCKED)
        await worker_bot.send_message(
            chat_id=feature.telegram_chat_id,
            message_thread_id=feature.telegram_thread_id,
            text=f"⏱ Таймаут: <b>{task.title}</b>", parse_mode="HTML",
        )
        return

    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")
    logger.info("Sandbox stdout for task {}:\n{}", task.id, out[-2000:])
    if proc.returncode != 0:
        logger.error("Sandbox stderr for task {} (exit {}):\n{}", task.id, proc.returncode, err[-2000:])
        await update_task_status(pool, task.id, TaskStatus.BLOCKED)
        await worker_bot.send_message(
            chat_id=feature.telegram_chat_id,
            message_thread_id=feature.telegram_thread_id,
            text=f"⛔ Упал: <b>{task.title}</b> (exit {proc.returncode}).",
            parse_mode="HTML",
        )
        return

    pr_number = _extract_pr_number(out)
    pr_url = _extract_pr_url(out)

    if pr_number is None:
        await update_task_status(pool, task.id, TaskStatus.BLOCKED)
        await worker_bot.send_message(
            chat_id=feature.telegram_chat_id,
            message_thread_id=feature.telegram_thread_id,
            text=f"⚠️ Завершил но PR не найден: <b>{task.title}</b>",
            parse_mode="HTML",
        )
        return

    await update_task_status(pool, task.id, TaskStatus.PR_OPEN, github_pr_number=pr_number)
    suffix = " (обновил PR)" if is_rerun else ""
    await worker_bot.send_message(
        chat_id=feature.telegram_chat_id,
        message_thread_id=feature.telegram_thread_id,
        text=f"✅ <b>{task.title}</b>{suffix}\nPR: {pr_url}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def _ensure_writable(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o777)
    except PermissionError as e:
        logger.warning("Cannot chmod {}: {}", path, e)


def _slugify(text: str) -> str:
    import re
    s = text.lower()
    s = re.sub(r"[^a-zа-я0-9]+", "-", s)
    s = s.strip("-")
    return s[:40] or "task"


def _extract_pr_url(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("PR_URL="):
            return line[len("PR_URL="):].strip()
    return None


def _extract_pr_number(stdout: str) -> int | None:
    url = _extract_pr_url(stdout)
    if not url:
        return None
    import re
    m = re.search(r"/pull/(\d+)", url)
    return int(m.group(1)) if m else None
