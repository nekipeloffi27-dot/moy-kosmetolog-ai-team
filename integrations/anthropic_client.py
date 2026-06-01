"""Anthropic SDK wrapper with logging, token counting, budget enforcement."""
from __future__ import annotations

import base64
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic, APITimeoutError
from loguru import logger

from core.budget import cost_cents
from core.config import get_settings
from services.features import add_budget_used, is_over_budget, mark_budget_alert_sent


class BudgetExceeded(Exception):
    pass


_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        kwargs = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_proxy_url:
            import httpx
            kwargs["http_client"] = httpx.AsyncClient(
                proxy=settings.anthropic_proxy_url,
                timeout=httpx.Timeout(900.0, connect=15.0),
            )
            logger.info("Anthropic SDK: using HTTPS proxy")
        _client = AsyncAnthropic(**kwargs)
    return _client


async def log_call(
    pool: asyncpg.Pool,
    *,
    feature_id: UUID,
    agent: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    success: bool,
    error: str | None = None,
    task_id: UUID | None = None,
) -> int:
    """Log an agent call. Returns cost in cents."""
    cents = cost_cents(model, input_tokens, output_tokens)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_calls
                (feature_id, task_id, agent, model, input_tokens, output_tokens,
                 cost_cents, duration_ms, success, error)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            feature_id, task_id, agent, model, input_tokens, output_tokens,
            cents, duration_ms, success, error,
        )
    budget = await add_budget_used(pool, feature_id, cents)
    await _maybe_fire_budget_alert(pool, feature_id, budget)
    return cents


def image_block_from_path(path: str) -> dict[str, Any]:
    """Build an Anthropic 'image' content block from a local file."""
    raw = Path(path).read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    media = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media, "data": b64},
    }


async def call_llm(
    *,
    pool: asyncpg.Pool,
    feature_id: UUID,
    agent: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 8000,
    task_id: UUID | None = None,
    tools: list[dict] | None = None,
    tool_executor: Callable[[str, dict], Awaitable[str]] | None = None,
    max_tool_iterations: int = 10,
) -> str:
    """LLM call with optional tool use loop. Logs cost, enforces budget cap.

    If *tools* is provided, runs a tool use loop (up to *max_tool_iterations*).
    Each API call is logged separately with an 'agent:iter=N' label.
    Calls without *tools* behave exactly as before (one call, one log entry).

    Returns the assembled text from all text blocks across all iterations.
    """
    if await is_over_budget(pool, feature_id):
        raise BudgetExceeded(f"Feature {feature_id} exceeded budget")

    client = get_client()

    if tools is None:
        return await _call_once(
            pool=pool, feature_id=feature_id, task_id=task_id,
            agent=agent, model=model, system=system,
            messages=messages, max_tokens=max_tokens,
            client=client,
        )

    return await _call_with_tools(
        pool=pool, feature_id=feature_id, task_id=task_id,
        agent=agent, model=model, system=system,
        messages=messages, max_tokens=max_tokens,
        tools=tools, tool_executor=tool_executor,
        max_tool_iterations=max_tool_iterations,
        client=client,
    )


async def _call_once(
    *,
    pool: asyncpg.Pool,
    feature_id: UUID,
    task_id: UUID | None,
    agent: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    client: AsyncAnthropic,
) -> str:
    """Single API call — original one-shot behaviour."""
    started = time.time()
    success = True
    error_text: str | None = None
    in_tok = out_tok = 0
    text_out = ""

    try:
        last_exc = None
        for attempt, backoff in enumerate([0, 5, 15], start=1):
            if backoff:
                logger.warning("Retry attempt {} for agent {} after {}s backoff", attempt, agent, backoff)
                import asyncio as _asyncio
                await _asyncio.sleep(backoff)
            try:
                resp = await client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                )
                last_exc = None
                break
            except APITimeoutError as e:
                last_exc = e
                logger.warning("APITimeoutError on attempt {} for agent {}: {}", attempt, agent, e)
                continue
        if last_exc is not None:
            raise last_exc
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        text_out = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
    except Exception as e:
        success = False
        error_text = str(e)
        logger.exception("LLM call failed for agent {}: {}", agent, e)
        raise
    finally:
        duration_ms = int((time.time() - started) * 1000)
        cents = await log_call(
            pool,
            feature_id=feature_id, task_id=task_id, agent=agent, model=model,
            input_tokens=in_tok, output_tokens=out_tok,
            duration_ms=duration_ms, success=success, error=error_text,
        )
        logger.info(
            "Agent {} | model={} | in={} out={} | {} ms | ${:.4f}",
            agent, model, in_tok, out_tok, duration_ms, cents / 100,
        )

    return text_out


async def _call_with_tools(
    *,
    pool: asyncpg.Pool,
    feature_id: UUID,
    task_id: UUID | None,
    agent: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    tools: list[dict],
    tool_executor: Callable[[str, dict], Awaitable[str]] | None,
    max_tool_iterations: int,
    client: AsyncAnthropic,
) -> str:
    """Tool use loop — calls LLM repeatedly until no tool_use blocks remain."""
    current_messages = list(messages)
    all_text_parts: list[str] = []

    for iteration in range(1, max_tool_iterations + 1):
        started = time.time()
        success = True
        error_text: str | None = None
        in_tok = out_tok = 0
        iter_label = f"{agent}:iter={iteration}"

        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=current_messages,
                tools=tools,
            )
            in_tok = resp.usage.input_tokens
            out_tok = resp.usage.output_tokens
        except Exception as e:
            success = False
            error_text = str(e)
            logger.exception("LLM tool-loop iter {} failed for agent {}: {}", iteration, agent, e)
            await log_call(
                pool,
                feature_id=feature_id, task_id=task_id,
                agent=iter_label, model=model,
                input_tokens=0, output_tokens=0,
                duration_ms=int((time.time() - started) * 1000),
                success=False, error=error_text,
            )
            raise
        finally:
            if success:
                duration_ms = int((time.time() - started) * 1000)
                cents = await log_call(
                    pool,
                    feature_id=feature_id, task_id=task_id,
                    agent=iter_label, model=model,
                    input_tokens=in_tok, output_tokens=out_tok,
                    duration_ms=duration_ms, success=True,
                )
                logger.info(
                    "Agent {} | model={} | in={} out={} | {} ms | ${:.4f}",
                    iter_label, model, in_tok, out_tok, duration_ms, cents / 100,
                )

        # Collect text and check for tool use
        tool_use_blocks = []
        assistant_content: list[dict[str, Any]] = []

        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                all_text_parts.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})
            elif btype == "tool_use":
                tool_use_blocks.append(block)
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        if not tool_use_blocks:
            # LLM returned only text — done
            break

        if tool_executor is None:
            logger.warning("LLM returned tool_use but no executor — stopping loop")
            break

        # Execute tools and build next turn
        current_messages.append({"role": "assistant", "content": assistant_content})

        tool_results: list[dict[str, Any]] = []
        for block in tool_use_blocks:
            logger.debug("Tool call: {} args={}", block.name, block.input)
            result = await tool_executor(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        current_messages.append({"role": "user", "content": tool_results})

    return "".join(all_text_parts)


async def _maybe_fire_budget_alert(pool, feature_id: UUID, budget: dict) -> None:
    """Post a Telegram alert if a budget threshold (50% or 90%) was just crossed."""
    cap = budget.get("cap", 0)
    if not cap:
        return

    used        = budget.get("used", 0)
    alerts_sent = budget.get("alerts_sent", [])
    ratio       = used / cap

    alert_level: int | None = None
    if ratio >= 0.9 and 90 not in alerts_sent:
        alert_level = 90
    elif ratio >= 0.5 and 50 not in alerts_sent:
        alert_level = 50

    if alert_level is None:
        return

    # Record first so re-entrant calls don't double-fire
    try:
        await mark_budget_alert_sent(pool, feature_id, alert_level)
    except Exception as e:
        logger.warning("Could not record budget alert for feature {}: {}", feature_id, e)
        return

    used_str = f"${used / 100:.2f}"
    cap_str  = f"${cap / 100:.2f}"
    icon     = "🚨" if alert_level == 90 else "⚠️"
    text = (
        f"{icon} Использовано {alert_level}% бюджета "
        f"({used_str} из {cap_str}).\n"
        f"Чтобы увеличить лимит — TODO: <code>/budget_cap &lt;cents&gt;</code>"
    )

    chat_id   = budget.get("chat_id", 0)
    thread_id = budget.get("thread_id", 0)
    if not chat_id:
        return

    try:
        from core.bots import get_bots
        bots = get_bots()
        await bots.pm.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=text,
            parse_mode="HTML",
        )
        logger.info(
            "Budget alert {}% fired for feature {} (used={}, cap={})",
            alert_level, feature_id, used, cap,
        )
    except RuntimeError:
        pass  # bots not initialized (e.g. CLI / test context)
    except Exception as e:
        logger.warning("Failed to send budget alert for feature {}: {}", feature_id, e)
