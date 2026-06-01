"""CTO Revert runner.

Triggered when a feature enters REVERTING. For each MERGED task with a
github_pr_number, creates a revert PR via git + gh CLI (shallow clone,
git revert, push, gh pr create). Posts results to the feature thread.

Outcome:
  - At least one revert PR created → REVERTED
  - All revert attempts failed    → FAILED
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from loguru import logger

from core.bots import BotRegistry
from core.config import get_settings
from core.enums import FeatureState, TaskStatus, TaskType
from core.orchestrator import register_agent
from core.state_machine import transition
from integrations.github import get_pr
from services.features import get_feature
from services.revert import RevertError, create_revert_pr
from services.tasks import list_tasks


REPO_BY_TYPE = {
    TaskType.BACKEND:         "github_repo_backend",
    TaskType.FRONTEND_WEB:    "github_repo_pwa",
    TaskType.FRONTEND_MOBILE: "github_repo_mobile",
}


@register_agent(FeatureState.REVERTING)
async def run_cto_revert(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    settings = get_settings()
    feature = await get_feature(pool, feature_id)
    if feature is None:
        logger.error("CTO revert called for missing feature {}", feature_id)
        return

    chat = feature.telegram_chat_id
    thread = feature.telegram_thread_id

    all_tasks = await list_tasks(pool, feature_id)
    merged = [t for t in all_tasks if t.status == TaskStatus.MERGED and t.github_pr_number]

    if not merged:
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text=(
                "⚠️ Нет смерджённых PR для отката.\n"
                "Если PR были смерджены вручную — откатывай вручную."
            ),
        )
        await transition(pool, feature_id, FeatureState.REVERTED,
                         actor="agent:cto_revert", reason="no merged PRs found")
        return

    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text=f"⏪ Откатываю {len(merged)} PR…",
    )

    successes: list[str] = []
    failures: list[str] = []

    for task in merged:
        repo_ref = getattr(settings, REPO_BY_TYPE[task.type])
        pr_number = task.github_pr_number

        try:
            pr_data = await get_pr(repo_ref, pr_number)
        except Exception as e:
            logger.error("Could not fetch PR #{}: {}", pr_number, e)
            failures.append(f"PR #{pr_number} ({task.title}): не удалось получить данные — {e}")
            continue

        merge_sha = pr_data.get("merge_commit_sha") or ""
        base_branch = (pr_data.get("base") or {}).get("ref") or settings.github_default_branch
        pr_title = pr_data.get("title") or task.title

        if not merge_sha:
            failures.append(f"PR #{pr_number} ({task.title}): merge_commit_sha пустой")
            continue

        try:
            revert_url = await create_revert_pr(
                repo_ref=repo_ref,
                pr_number=pr_number,
                pr_title=pr_title,
                merge_commit_sha=merge_sha,
                base_branch=base_branch,
            )
            successes.append(
                f"✅ <a href='{revert_url}'>Revert PR #{pr_number}</a> — {task.title}"
            )
        except RevertError as e:
            logger.error("Revert failed for PR #{}: {}", pr_number, e)
            failures.append(f"PR #{pr_number} ({task.title}): {e}")

    # ─── Post results ───
    lines = ["<b>⏪ Результат отката</b>\n"]
    if successes:
        lines.append("<b>Созданы revert PR:</b>")
        lines.extend(successes)
    if failures:
        lines.append("\n<b>Не удалось откатить:</b>")
        lines.extend(f"❌ {f}" for f in failures)

    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text="\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    if successes:
        await transition(pool, feature_id, FeatureState.REVERTED,
                         actor="agent:cto_revert",
                         reason=f"reverted {len(successes)}/{len(merged)} PRs")
    else:
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text="⛔ Ни один PR не удалось откатить автоматически. Откатывай вручную.",
        )
        await transition(pool, feature_id, FeatureState.FAILED,
                         actor="agent:cto_revert", reason="all revert attempts failed")

    logger.info(
        "CTO revert for feature {}: {}/{} PRs reverted",
        feature_id, len(successes), len(merged),
    )
