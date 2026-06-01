"""Budget reporting — feature-level and global cost summaries."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg

from core.enums import FEATURE_STATE_LABELS_RU, FeatureState

_PERIOD_WHERE = {
    "today": "created_at >= current_date",
    "week":  "created_at >= current_date - interval '6 days'",
    "month": "created_at >= current_date - interval '29 days'",
    "all":   "TRUE",
}

_PERIOD_LABELS = {
    "today": "Сегодня",
    "week":  "7 дней",
    "month": "30 дней",
    "all":   "Всё время",
}

_AGENT_NAMES: dict[str, str] = {
    "pm":                  "PM",
    "designer":            "Designer",
    "cto_tasking":         "CTO",
    "cto_review":          "CTO Review",
    "cto_deploy":          "Deploy",
    "cto_ops":             "Ops",
    "cto_revert":          "Revert",
    "backend_dev":         "Backend Dev",
    "frontend_web_dev":    "Frontend Dev",
    "frontend_mobile_dev": "Mobile Dev",
}


async def get_feature_report(pool: asyncpg.Pool, feature_id: UUID) -> dict:
    """
    Returns {
        feature_id, title, state, total_cents, cap_cents,
        started_at, completed_at, duration_minutes,
        by_agent: [{agent, calls, cost_cents, percent}],
        by_task:  [{task_id, task_title, cost_cents}],
    }
    """
    async with pool.acquire() as conn:
        feature_row = await conn.fetchrow(
            """
            SELECT id, title, state, budget_used_cents, budget_cap_cents,
                   created_at, completed_at
            FROM features WHERE id = $1
            """,
            feature_id,
        )
        if feature_row is None:
            raise ValueError(f"Feature {feature_id} not found")

        by_agent_rows = await conn.fetch(
            """
            SELECT
                split_part(agent, ':', 1) AS agent,
                COUNT(*)::int                AS calls,
                SUM(cost_cents)::int         AS cost_cents
            FROM agent_calls
            WHERE feature_id = $1
            GROUP BY split_part(agent, ':', 1)
            ORDER BY cost_cents DESC
            """,
            feature_id,
        )

        by_task_rows = await conn.fetch(
            """
            SELECT
                t.id           AS task_id,
                t.title        AS task_title,
                SUM(ac.cost_cents)::int AS cost_cents
            FROM agent_calls ac
            JOIN tasks t ON ac.task_id = t.id
            WHERE ac.feature_id = $1 AND ac.task_id IS NOT NULL
            GROUP BY t.id, t.title
            ORDER BY cost_cents DESC
            """,
            feature_id,
        )

    f = dict(feature_row)
    agent_total = sum(r["cost_cents"] for r in by_agent_rows) or 0

    by_agent = [
        {
            "agent":      r["agent"],
            "calls":      r["calls"],
            "cost_cents": r["cost_cents"],
            "percent":    round(r["cost_cents"] / agent_total * 100, 1) if agent_total else 0.0,
        }
        for r in by_agent_rows
    ]

    by_task = [
        {
            "task_id":    str(r["task_id"]),
            "task_title": r["task_title"],
            "cost_cents": r["cost_cents"],
        }
        for r in by_task_rows
    ]

    duration: int | None = None
    if f.get("completed_at") and f.get("created_at"):
        delta = f["completed_at"] - f["created_at"]
        duration = max(1, int(delta.total_seconds() / 60))

    return {
        "feature_id":      feature_id,
        "title":           f["title"],
        "state":           f["state"],
        "total_cents":     f["budget_used_cents"],
        "cap_cents":       f["budget_cap_cents"],
        "started_at":      f["created_at"],
        "completed_at":    f.get("completed_at"),
        "duration_minutes": duration,
        "by_agent":        by_agent,
        "by_task":         by_task,
    }


async def get_global_report(pool: asyncpg.Pool, period: str) -> dict:
    """
    period: 'today' | 'week' | 'month' | 'all'
    Returns {
        period, feature_count, total_cents,
        top_features: [{feature_id, title, cost_cents}],
        by_agent: [{agent, calls, cost_cents, percent}],
    }
    """
    if period not in _PERIOD_WHERE:
        period = "today"

    where = _PERIOD_WHERE[period]

    async with pool.acquire() as conn:
        summary_row = await conn.fetchrow(
            f"""
            SELECT
                COUNT(DISTINCT feature_id)::int AS feature_count,
                COALESCE(SUM(cost_cents), 0)::int AS total_cents
            FROM agent_calls
            WHERE {where}
            """,
        )

        by_agent_rows = await conn.fetch(
            f"""
            SELECT
                split_part(agent, ':', 1) AS agent,
                COUNT(*)::int               AS calls,
                SUM(cost_cents)::int        AS cost_cents
            FROM agent_calls
            WHERE {where}
            GROUP BY split_part(agent, ':', 1)
            ORDER BY cost_cents DESC
            """,
        )

        top_rows = await conn.fetch(
            f"""
            SELECT
                f.id    AS feature_id,
                f.title AS title,
                COALESCE(SUM(ac.cost_cents), 0)::int AS cost_cents
            FROM agent_calls ac
            JOIN features f ON ac.feature_id = f.id
            WHERE {where.replace('created_at', 'ac.created_at')}
            GROUP BY f.id, f.title
            ORDER BY cost_cents DESC
            LIMIT 3
            """,
        )

    s = dict(summary_row)
    agent_total = s["total_cents"] or 0

    by_agent = [
        {
            "agent":      r["agent"],
            "calls":      r["calls"],
            "cost_cents": r["cost_cents"],
            "percent":    round(r["cost_cents"] / agent_total * 100, 1) if agent_total else 0.0,
        }
        for r in by_agent_rows
    ]

    top_features = [
        {
            "feature_id": str(r["feature_id"]),
            "title":      r["title"],
            "cost_cents": r["cost_cents"],
        }
        for r in top_rows
    ]

    return {
        "period":        period,
        "feature_count": s["feature_count"],
        "total_cents":   agent_total,
        "top_features":  top_features,
        "by_agent":      by_agent,
    }


def format_feature_report(report: dict) -> str:
    """HTML-formatted for Telegram."""
    used   = report["total_cents"]
    cap    = report["cap_cents"]
    pct    = f"{used / cap * 100:.0f}%" if cap else "—"

    try:
        state_label = FEATURE_STATE_LABELS_RU[FeatureState(report["state"])]
    except (KeyError, ValueError):
        state_label = report["state"]

    lines = [
        f"<b>📊 {_esc(report['title'])}</b>",
        f"Статус: {state_label}",
        f"Потрачено: <b>${used / 100:.2f}</b> из ${cap / 100:.2f} ({pct})",
    ]
    if report.get("duration_minutes") is not None:
        lines.append(f"Время: {report['duration_minutes']} мин")

    if report["by_agent"]:
        lines += ["", "<b>💰 По агентам:</b>"]
        for a in report["by_agent"]:
            name = _AGENT_NAMES.get(a["agent"], a["agent"])
            lines.append(
                f"• {_esc(name)} — <b>${a['cost_cents'] / 100:.2f}</b>"
                f" ({a['calls']} вызов{'ов' if a['calls'] != 1 else ''})"
            )

    if report["by_task"]:
        lines += ["", "<b>📌 По задачам:</b>"]
        for t in report["by_task"]:
            lines.append(
                f"• {_esc(t['task_title'][:50])} — ${t['cost_cents'] / 100:.2f}"
            )

    return "\n".join(lines)


def format_global_report(report: dict) -> str:
    """HTML-formatted for Telegram."""
    period_label = _PERIOD_LABELS.get(report["period"], report["period"])
    total = report["total_cents"]

    lines = [
        f"<b>📊 Расходы: {period_label}</b>",
        f"Фич: {report['feature_count']}",
        f"Итого: <b>${total / 100:.2f}</b>",
    ]

    if report["by_agent"]:
        lines += ["", "<b>💰 По агентам:</b>"]
        for a in report["by_agent"]:
            name = _AGENT_NAMES.get(a["agent"], a["agent"])
            lines.append(
                f"• {_esc(name)} — <b>${a['cost_cents'] / 100:.2f}</b>"
                f" ({a['calls']} вызов{'ов' if a['calls'] != 1 else ''})"
            )

    if report["top_features"]:
        lines += ["", "<b>🏆 Топ фичи:</b>"]
        for f in report["top_features"]:
            lines.append(
                f"• {_esc(f['title'][:40])} — ${f['cost_cents'] / 100:.2f}"
            )

    return "\n".join(lines)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
