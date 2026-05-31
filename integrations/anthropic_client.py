"""Anthropic SDK wrapper with logging, token counting, budget enforcement."""
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic
from loguru import logger

from core.budget import cost_cents
from core.config import get_settings
from services.features import add_budget_used, is_over_budget


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
                timeout=httpx.Timeout(120.0, connect=10.0),
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
    await add_budget_used(pool, feature_id, cents)
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
) -> str:
    """One-shot LLM call. Logs cost, enforces budget cap.

    Returns the assembled text from all text blocks in the response.
    """
    if await is_over_budget(pool, feature_id):
        raise BudgetExceeded(f"Feature {feature_id} exceeded budget")

    client = get_client()
    started = time.time()
    success = True
    error_text: str | None = None
    in_tok = out_tok = 0
    text_out = ""

    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
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
