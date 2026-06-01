"""Pydantic models mirroring DB rows. Used everywhere instead of raw dicts."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from core.enums import FeatureState, TaskStatus, TaskType


class Feature(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    screenshot_path: str | None
    telegram_chat_id: int
    telegram_thread_id: int
    telegram_user_id: int
    state: FeatureState
    context: dict[str, Any] = {}
    clarification_history: list[dict[str, Any]] = []
    budget_used_cents: int = 0
    budget_cap_cents: int = 500
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class Task(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feature_id: UUID
    type: TaskType
    title: str
    description: str
    github_issue_number: int | None = None
    github_pr_number: int | None = None
    branch_name: str | None = None
    status: TaskStatus
    complexity: str = "medium"
    affected_files: list[str] = []
    changes_per_file: list[dict] = []
    do_not_touch: list[str] = []
    references: list[dict] = []
    verification: str | None = None
    expected_diff_size: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentCall(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feature_id: UUID
    task_id: UUID | None = None
    agent: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_cents: int = 0
    duration_ms: int | None = None
    success: bool = True
    error: str | None = None
    created_at: datetime


class StateTransition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feature_id: UUID
    from_state: FeatureState | None
    to_state: FeatureState
    reason: str | None
    actor: str
    created_at: datetime
