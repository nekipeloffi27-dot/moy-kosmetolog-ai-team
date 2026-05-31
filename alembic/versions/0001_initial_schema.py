"""Initial schema: features, tasks, agent_calls, state_transitions.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-31

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE feature_state AS ENUM (
            'design_pending',
            'design_review',
            'tasks_pending',
            'coding',
            'review',
            'dev_deployed',
            'testing',
            'prod_ready',
            'prod_deployed',
            'blocked',
            'failed'
        );

        CREATE TYPE task_type AS ENUM (
            'backend',
            'frontend_web',
            'frontend_mobile'
        );

        CREATE TYPE task_status AS ENUM (
            'pending',
            'in_progress',
            'pr_open',
            'merged',
            'blocked'
        );

        CREATE TABLE features (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title               TEXT NOT NULL,
            description         TEXT NOT NULL,
            screenshot_path     TEXT,
            telegram_chat_id    BIGINT NOT NULL,
            telegram_thread_id  BIGINT NOT NULL,
            telegram_user_id    BIGINT NOT NULL,
            state               feature_state NOT NULL DEFAULT 'design_pending',
            context             JSONB NOT NULL DEFAULT '{}'::jsonb,
            budget_used_cents   INT NOT NULL DEFAULT 0,
            budget_cap_cents    INT NOT NULL DEFAULT 500,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at        TIMESTAMPTZ
        );

        CREATE INDEX idx_features_state    ON features(state);
        CREATE INDEX idx_features_thread   ON features(telegram_chat_id, telegram_thread_id);
        CREATE INDEX idx_features_user     ON features(telegram_user_id);

        CREATE TABLE tasks (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            feature_id           UUID NOT NULL REFERENCES features(id) ON DELETE CASCADE,
            type                 task_type NOT NULL,
            title                TEXT NOT NULL,
            description          TEXT NOT NULL,
            github_issue_number  INT,
            github_pr_number     INT,
            branch_name          TEXT,
            status               task_status NOT NULL DEFAULT 'pending',
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX idx_tasks_feature  ON tasks(feature_id);
        CREATE INDEX idx_tasks_status   ON tasks(status);
        CREATE INDEX idx_tasks_type     ON tasks(type);

        CREATE TABLE agent_calls (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            feature_id      UUID NOT NULL REFERENCES features(id) ON DELETE CASCADE,
            task_id         UUID REFERENCES tasks(id) ON DELETE SET NULL,
            agent           TEXT NOT NULL,
            model           TEXT NOT NULL,
            input_tokens    INT NOT NULL DEFAULT 0,
            output_tokens   INT NOT NULL DEFAULT 0,
            cost_cents      INT NOT NULL DEFAULT 0,
            duration_ms     INT,
            success         BOOLEAN NOT NULL DEFAULT TRUE,
            error           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX idx_calls_feature  ON agent_calls(feature_id);
        CREATE INDEX idx_calls_agent    ON agent_calls(agent);
        CREATE INDEX idx_calls_created  ON agent_calls(created_at DESC);

        CREATE TABLE state_transitions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            feature_id  UUID NOT NULL REFERENCES features(id) ON DELETE CASCADE,
            from_state  feature_state,
            to_state    feature_state NOT NULL,
            reason      TEXT,
            actor       TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX idx_transitions_feature  ON state_transitions(feature_id);
        CREATE INDEX idx_transitions_created  ON state_transitions(created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS state_transitions;
        DROP TABLE IF EXISTS agent_calls;
        DROP TABLE IF EXISTS tasks;
        DROP TABLE IF EXISTS features;
        DROP TYPE IF EXISTS task_status;
        DROP TYPE IF EXISTS task_type;
        DROP TYPE IF EXISTS feature_state;
        """
    )
