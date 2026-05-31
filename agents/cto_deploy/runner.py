"""CTO Deploy runner.

Two registrations:
- DEV_DEPLOYED state → runs `DEPLOY_DEV_COMMAND`, transitions to TESTING.
- PROD_READY state   → runs `DEPLOY_PROD_COMMAND`, transitions to PROD_DEPLOYED.

If the corresponding command is empty in .env, we skip the deploy and just
transition forward — useful for initial setup before deployment is wired.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from loguru import logger

from core.bots import BotRegistry
from core.config import get_settings
from core.enums import FeatureState
from core.orchestrator import register_agent
from core.state_machine import transition
from integrations.deploy import run_deploy_command
from services.features import get_feature, update_context


@register_agent(FeatureState.DEV_DEPLOYED)
async def run_dev_deploy(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    settings = get_settings()
    await _do_deploy(
        feature_id=feature_id,
        bots=bots,
        pool=pool,
        cmd=settings.deploy_dev_command,
        timeout=settings.deploy_timeout,
        env_label="dev",
        on_success_state=FeatureState.TESTING,
        on_success_message=(
            "✅ Задеплоил на dev. Иди тестировать.\n"
            "Когда проверишь:\n"
            "<code>/pass_test</code> — всё ок, готовим к проду\n"
            "<code>/fail_test что не так</code> — нашёл проблемы, обратно в работу"
        ),
        success_actor="agent:cto_deploy:dev",
    )


@register_agent(FeatureState.PROD_READY)
async def run_prod_deploy(feature_id: UUID, bots: BotRegistry, pool: asyncpg.Pool) -> None:
    settings = get_settings()
    await _do_deploy(
        feature_id=feature_id,
        bots=bots,
        pool=pool,
        cmd=settings.deploy_prod_command,
        timeout=settings.deploy_timeout,
        env_label="prod",
        on_success_state=FeatureState.PROD_DEPLOYED,
        on_success_message="🎉 Прод-деплой завершён. Фича в проде.",
        success_actor="agent:cto_deploy:prod",
    )


async def _do_deploy(
    *,
    feature_id: UUID,
    bots: BotRegistry,
    pool: asyncpg.Pool,
    cmd: str,
    timeout: int,
    env_label: str,
    on_success_state: FeatureState,
    on_success_message: str,
    success_actor: str,
) -> None:
    feature = await get_feature(pool, feature_id)
    if feature is None:
        return

    chat = feature.telegram_chat_id
    thread = feature.telegram_thread_id

    # Empty command → skip deploy, transition anyway. Useful before deploy is wired.
    if not cmd.strip():
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text=(
                f"⚠️ <code>DEPLOY_{env_label.upper()}_COMMAND</code> не задана. "
                f"Пропускаю деплой и иду дальше."
            ),
            parse_mode="HTML",
        )
        await transition(pool, feature_id, on_success_state,
                         actor=success_actor, reason=f"{env_label} deploy skipped (no command)")
        return

    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text=f"🚀 Деплою на {env_label}…",
    )

    logger.info("Running {} deploy for feature {}: {}", env_label, feature_id, cmd[:200])
    success, output = await run_deploy_command(cmd, timeout)

    # Save the tail of the output to feature context for forensics
    await update_context(pool, feature_id, **{
        f"{env_label}_deploy_output_tail": output[-3000:],
        f"{env_label}_deploy_success": success,
    })

    if success:
        await bots.cto.send_message(
            chat_id=chat, message_thread_id=thread,
            text=on_success_message,
            parse_mode="HTML",
        )
        await transition(pool, feature_id, on_success_state,
                         actor=success_actor, reason=f"{env_label} deploy succeeded")
        return

    # Failed
    tail = output[-1500:] if output else "(no output)"
    await bots.cto.send_message(
        chat_id=chat, message_thread_id=thread,
        text=(
            f"⛔ Деплой на {env_label} упал. Хвост вывода:\n"
            f"<pre>{_html_escape(tail)}</pre>"
        ),
        parse_mode="HTML",
    )
    await transition(pool, feature_id, FeatureState.BLOCKED,
                     actor=success_actor, reason=f"{env_label} deploy failed")


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))
